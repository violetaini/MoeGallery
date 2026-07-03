from fastapi import Query


def pagination_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
) -> tuple[int, int]:
    return page, page_size


def parse_id_csv(value: str | None) -> list[int] | None:
    if value is None or value.strip() == "":
        return None
    ids: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            ids.append(int(part))
    return ids

