class ToolInputError(ValueError):
    """The arguments given to a tool were invalid, so no provider was called.

    `problems` names each bad field and why ("travellers: Input should be ..."). It
    never repeats the rejected values: they may be untrusted text (SECURITY §3).
    """

    def __init__(self, tool_name: str, problems: tuple[str, ...]) -> None:
        super().__init__(f"{tool_name}: invalid input ({'; '.join(problems)})")
        self.tool_name = tool_name
        self.problems = problems
