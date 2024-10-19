from shlex import quote


class SSHContainer:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def start_container(self) -> str:
        result = await self.connection.run(
            "docker run -d --network=container:gluetun --rm ai-ssh tail -f /dev/null"
        )
        return result.stdout.strip()

    async def stop_container(self, container_id: str) -> None:
        await self.connection.run(f"docker stop {quote(container_id)}")

    async def force_stop_container(self, container_id: str) -> None:
        await self.connection.run(f"docker rm -f {quote(container_id)}")

    async def exec_in_container(self, container_id: str, cmd: str):
        safe_container_id = quote(container_id)
        safe_cmd = quote(cmd)
        result = await self.connection.run(
            f"docker exec {safe_container_id} /bin/sh -c {safe_cmd}"
        )

        return {
            "command": cmd,
            "output": result.stdout,
            "error": result.stderr,
            "exit_code": result.exit_status,
        }


class PythonContainer:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def start_container(self) -> str:
        result = await self.connection.run(
            "docker run -d --network=container:gluetun --rm ai-python tail -f /dev/null"
        )
        return result.stdout.strip()

    async def stop_container(self, container_id: str) -> None:
        await self.connection.run(f"docker stop {quote(container_id)}")

    async def force_stop_container(self, container_id: str) -> None:
        await self.connection.run(f"docker rm -f {quote(container_id)}")

    async def exec_in_container(self, container_id: str, cmd: str):
        safe_container_id = quote(container_id)
        safe_cmd = quote(cmd)
        result = await self.connection.run(
            f"docker exec {safe_container_id} python3 -c {safe_cmd}"
        )

        return {
            "command": cmd,
            "output": result.stdout,
            "error": result.stderr,
            "exit_code": result.exit_status,
        }

    async def write_file_in_container(
        self, container_id: str, file_content: str, file_name: str = "script.py"
    ):
        safe_container_id = quote(container_id)
        safe_file_content = quote(file_content)
        safe_file_name = quote(file_name)

        cmd = f"echo {safe_file_content} > {safe_file_name}"
        await self.connection.run(
            f"docker exec {safe_container_id} /bin/sh -c {quote(cmd)}"
        )

    async def run_python_file(self, container_id: str, file_name: str = "script.py"):
        safe_container_id = quote(container_id)
        safe_file_name = quote(file_name)

        result = await self.connection.run(
            f"docker exec {safe_container_id} python3 {safe_file_name}"
        )

        return {
            "command": f"python3 {file_name}",
            "output": result.stdout,
            "error": result.stderr,
            "exit_code": result.exit_status,
        }
