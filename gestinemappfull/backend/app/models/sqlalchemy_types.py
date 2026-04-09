from sqlalchemy import Enum as SqlEnum


def enum_column(enum_cls, name: str) -> SqlEnum:
    return SqlEnum(
        enum_cls,
        name=name,
        values_callable=lambda enum_type: [member.value for member in enum_type],
    )
