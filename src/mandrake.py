#!/usr/bin/env python3

import sys
import requests
import time

import tomli
import tomli_w
import sysrsync as rsync
from pathlib import Path

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
    parser.add_argument('-m', '--mandrakefile', type=Path, default=Path('Mandrake.toml'))
    parser.add_argument('-i', '--ignorefile', type=Path, default=Path('.mandrakeignore'))
    parser.add_argument('-r', '--remote', type=str, default=None)
    parser.add_argument('-f', '--force', action='store_true')
    parser.add_argument('-c', '--create', action='store_true')
    parser.add_argument('command', nargs="+")
    return parser.parse_args()


def get_remote(config, args):
    if len(config['remotes']) < 1:
        raise ValueError(f"No remotes defined in {args.mandrakefile}")

    if args.remote is not None:
        for remote in config['remotes']:
            if remote['name'] == args.remote:
                return remote

        raise ValueError(f"Remote '{args.remote}' not found in config")

    for remote in config['remotes']:
        if remote['default']:
            return remote

    return config['remotes'][0]


def create_job(remote):
    print(f"{remote['host']}/jobs")
    return requests.post(f"{remote['host']}/jobs").json()

def send_context(remote, job, ignorefile):
    # TODO ignore files in .dockerignore and .gitignore
    options = ['--recursive', '--update', '-v']
    if ignorefile.exists():
        options.append(f"--exclude-from={ignorefile}")

    rsync.run(
            source=".",
            destination=job['context_dir'],
            destination_ssh=remote['ssh']['host'],
            options=options,
            )


def sync_output_folder(remote, job, output_folder):
    options = ['--recursive', '--update', '-v']
    source_folder = f"{job['context_dir']}/{output_folder}"
    destination_folder = output_folder
    
    rsync.run(
            source = source_folder,
            source_ssh = remote['ssh']['host'],
            destination = destination_folder,
            options = options,
            )


def get_job_status(remote, job_id):
    return requests.get(f"{remote['host']}/jobs/{job_id}").json()


def send_command(remote, job, command):
    requests.patch(f"{remote['host']}/jobs/{job['id']}", json = {
        'state': STATE_CONTEXT_DELIVERED,
        'params': {
            'command': command
            }
        })


def main(args):
    """ Entry point for script """
    print("Reading config...")
    config = tomli.loads(args.mandrakefile.read_text())
    print(f"{config =}")
    remote = get_remote(config, args)
    print(f"{remote =}")
    print("Detecting job or creating job...")
    job_id = remote.get('job-id')
    if job_id is None or args.create:
        print("Job not present in config for remote. Creating...")
        job_id = create_job(remote)['id']
        print(f"Saving job_id to {args.mandrakefile}")
        remote['job-id'] = job_id
        args.mandrakefile.write_text(tomli_w.dumps(config))

    print("Retreiving job status...")
    job = get_job_status(remote, job_id)
    oldstate = None
    print(f"{job =}")
    while job['state'] not in [ STATE_BUILD_FAILED, STATE_RUNNING_FAILED, STATE_FINISED, STATE_WAITING ]:
        if args.force:
            break

        job = get_job_status(remote, job_id)
        if job != oldstate:
            print(f"Job already in progress (pass -f to force): {job =}")
            oldstate = job

    print("Sending context via rsync...")
    send_context(remote, job, args.ignorefile)
    print(f"Executing command on remote server: {args.command}")
    send_command(remote, job, args.command)

    while True:
        job = get_job_status(remote, job_id)
        if job != oldstate:
            print(f"{job=}")
            oldstate = job

        if job['state'] in [ STATE_BUILD_FAILED, STATE_RUNNING_FAILED, STATE_FINISED ]:
            if 'err' in job.keys():
                print(job['err'])
                return 1

        if job['state'] == STATE_FINISED:
            sync_output_folder(remote, job, config['defaults']['output'])
            print(f"{job=}")
            return 0

        time.sleep(1)

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(get_args()))
    except KeyboardInterrupt:
        sys.exit(0)
