"""Exit codes and the exceptions that carry them (spec A6)."""

OK, CHECK_FAILED, USAGE, ART_FAIL, NEEDS_INPUT = 0, 1, 2, 3, 4


class ShowcaseError(Exception):
    """An error with a CLI exit code and a §12.2 log code."""

    code = USAGE
    log = "usage"

    def __init__(self, message: str, log: str | None = None, code: int | None = None):
        super().__init__(message)
        if log is not None:
            self.log = log
        if code is not None:
            self.code = code


class ConfigError(ShowcaseError):
    code, log = USAGE, "config"


class Refused(ShowcaseError):
    """Excluded, hold or T3 owner: every command refuses (exit 2)."""

    code, log = USAGE, "hold"


class ArtFail(ShowcaseError):
    """Text does not fit any ladder step; nothing is written (exit 3)."""

    code, log = ART_FAIL, "art-fail"

    def __init__(self, element: str, text: str = ""):
        super().__init__(f"art-fail:{element}: {text!r} does not fit", log=f"art-fail:{element}")
        self.element, self.text = element, text


class NeedsInput(ShowcaseError):
    code, log = NEEDS_INPUT, "needs-input"

    def __init__(self, detail: str, message: str = ""):
        super().__init__(message or f"needs-input:{detail}", log=f"needs-input:{detail}")
        self.detail = detail
