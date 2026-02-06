class DeckBuilderError(Exception):
    pass

class InvalidLeaderIdError(DeckBuilderError):
    pass

class LeaderNotFoundError(DeckBuilderError):
    pass

class LeaderNotALeaderError(DeckBuilderError):
    pass

class ApiUnavailableError(DeckBuilderError):
    pass
