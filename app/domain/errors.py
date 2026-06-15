class DomainError(Exception):
    code = "domain_error"
    status = 400

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details


class InvalidWindowError(DomainError):
    code = "invalid_window"
    status = 422


class NoAssetValidError(DomainError):
    code = "no_asset_valid"
    status = 404
