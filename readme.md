# 🍃 mandrake

> (Proof of concept) run commands in remote docker container to offload compute intensive commands


## Usage

1. Create `config-server.toml`.
   See [`config-servre.toml`](./config-server.toml) for an example.
1. Start `mandrake-server.py`
1. Create `Mandrake.toml` file in root directory of project.
   See [`Mandrake.toml`](Mandrake.toml) for an example.
1. Create a `Dockerfile` in the root directory of project to specify the environment to
   execute the command.
   See [`Dockerfile-example`](Dockerfile-example) for an example.

   Remember to the working directory to `/context`.

1. Run `mandrake-server.py <command> [arg1 [arg2 [...]]]` in the project directory,
   where `<command>` and `[argN]` the command and its arguments to run in the docker
   container.
