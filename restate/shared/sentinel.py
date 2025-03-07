class SingletonMeta(type):
    _instances = {}

    def __call__(cls, identifier: str):
        if identifier not in cls._instances:
            cls._instances[identifier] = super().__call__(identifier)
        return cls._instances[identifier]


class Sentinel(metaclass=SingletonMeta):
    def __init__(self, identifier: str):
        self.identifier = identifier

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sentinel):
            return False

        return self.identifier == other.identifier

    def __repr__(self) -> str:
        return f"Sentinel({self.identifier})"

    def __hash__(self):
        return hash(self.identifier)


known: dict[str, Sentinel] = {}
