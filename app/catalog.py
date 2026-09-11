SERVICE_CATALOG = {
    "text_generation": "Text / content generation",
    "research_report": "Research & reports",
    "code_review": "Code review / small dev tasks",
    "translation": "Translation",
}


def is_valid_service(service_key: str) -> bool:
    return service_key in SERVICE_CATALOG


def service_label(service_key: str) -> str:
    return SERVICE_CATALOG.get(service_key, service_key)
