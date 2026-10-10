class McpError(Exception):
    pass


class SkillGraphError(McpError):
    pass


class ToolFailure(Exception):
    def __init__(self, status: int, *, retry: bool, retry_after: float | None = None) -> None:
        self.status = status
        self.retry = retry
        self.retry_after = retry_after
        super().__init__(f"status {status}")
