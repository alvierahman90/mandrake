#!/usr/bin/env python3


import concurrent.futures
import pathlib as pl
import sys
import json
import uuid
import traceback
import time


import docker
import tomli


from flask import Flask, request


STATE_WAITING = "WAITING"
STATE_CONTEXT_DELIVERED = "CONTEXT_DELIVERED"
STATE_SUBMITTED_TO_POOL = "SUBMITTED_TO_POOL"
STATE_BUILDING_CONTAINER = "BUILDING_CONTAINER"
STATE_BUILD_FAILED = "BUILD_FAILED"
STATE_RUNNING = "RUNNING"
STATE_RUNNING_FAILED = "RUNNING_FAILED"
STATE_FINISED = "FINISHED"



def get_args():
    """ Get command line arguments """

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=pl.Path)
    return parser.parse_args()


args = get_args()
config = tomli.loads(args.config.read_text())

def get_docker_daemon(config):
    base_url = config.get('docker-daemon-url')
    base_url = base_url or "unix:///var/run/docker.sock"

    return docker.DockerClient(base_url=base_url)

dock = get_docker_daemon(config)
app = Flask(__name__)

state = {}
pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


@app.route("/jobs", methods = [ "POST" ])
def post_jobs():
    job_id = str(uuid.uuid4())
    job = {
            "id": job_id,
            "state": STATE_WAITING,
            "context_dir":  f"{config['context-dir']}/{job_id}",
            }
    state[job['id']] = job

    return json.dumps(job)

def submit_job(job_id, params):
    tag = f"mandrake-job-{job_id}"
    path = f"{config['context-dir']}/{job_id}"
    def func():
        state[job_id]['state'] = STATE_BUILDING_CONTAINER
        try:
            (image, _) = dock.images.build(
                    path=path,
                    tag=tag,
                    )
        except Exception as e:
            state[job_id]['state'] = STATE_BUILD_FAILED
            state[job_id]['err'] = '\n'.join(traceback.format_exception(e))
            return

        state[job_id]['state'] = STATE_RUNNING

        container = None
        try:
            container = dock.containers.run(
                    image = image.id,
                    volumes = {
                        path: {
                            'bind': '/context',
                            'mode': 'rw',
                            }
                        },
                    detach=True,
                    **params,
                    )
        except Exception as e:
            state[job_id]['state'] = STATE_RUNNING_FAILED
            state[job_id]['err'] = '\n'.join(traceback.format_exception(e))
            return

        while True:
            time.sleep(1)
            container = dock.containers.get(container.id)
            print(f"{container.status=}")
            print( container.status not in [ 'created', 'running' ])
            if  container.status not in [ 'created', 'running' ]:
                break

        state[job_id]['state'] = STATE_FINISED
        output = container.attach(stdout=True, stderr=True, logs=True)
        state[job_id]['output'] = output.decode("utf-8")

    return func

@app.route("/jobs/<job_id>", methods = [ "PATCH" ])
def patch_job(job_id):
    new_state = request.get_json()['state']
    params = request.get_json()['params']

    state[job_id]['state'] = new_state

    if new_state == STATE_CONTEXT_DELIVERED:
        state[job_id]['state'] = STATE_SUBMITTED_TO_POOL
        pool.submit(submit_job(job_id, params))

    return json.dumps(state[job_id])

@app.route("/jobs")
def get_jobs():
    return json.dumps(state)


@app.route("/jobs/<job_id>")
def get_job(job_id):
    return json.dumps(state[job_id])

if __name__ == "__main__":
    app.run(debug=True)
