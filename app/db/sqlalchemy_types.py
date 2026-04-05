from sqlalchemy import Enum as SqlEnum

def values_enum(enum_cls, name: str):
    return SqlEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [e.value for e in cls],
        validate_strings=True,
        native_enum=True,
        create_constraint=False,
    )