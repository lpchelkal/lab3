"""Стартовый код сервиса тикетов техподдержки.

Часть классов и функций уже реализована, часть содержит TODO.
Структура данных тикета и правила перехода статуса заданы ниже.
Логику репозитория, сервиса и части эндпоинтов нужно доделать.
"""

from datetime import datetime
from enum import Enum
from functools import lru_cache

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


# --- Конфиг ---------------------------------------------------------------

class Settings(BaseModel):
    default_page_size: int = 5
    max_page_size: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- Исключения -------------------------------------------------------------

class HelpDeskError(Exception):
    """Базовое исключение сервиса."""


class TicketNotFoundError(HelpDeskError):
    def __init__(self, ticket_id: int) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"Тикет {ticket_id} не найден")


class InvalidStatusTransitionError(HelpDeskError):
    def __init__(self, current: "TicketStatus", target: "TicketStatus") -> None:
        self.current = current
        self.target = target
        super().__init__(f"Переход {current} -> {target} запрещён")


# --- Схемы ------------------------------------------------------------------

class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class TicketStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.open: {TicketStatus.in_progress},
    TicketStatus.in_progress: {TicketStatus.resolved, TicketStatus.open},
    TicketStatus.resolved: {TicketStatus.closed, TicketStatus.in_progress},
    TicketStatus.closed: set(),
}


class TicketCreate(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None
    priority: Priority = Priority.normal
    assignee: str | None = None


class TicketUpdate(BaseModel):
    description: str | None = None
    priority: Priority | None = None
    assignee: str | None = None
    status: TicketStatus | None = None


class Ticket(BaseModel):
    id: int
    title: str
    description: str | None
    priority: Priority
    status: TicketStatus
    assignee: str | None
    created_at: datetime


class TicketPage(BaseModel):
    items: list[Ticket]
    total: int
    page: int
    page_size: int


# --- Репозиторий --------------------------------------------------------------

class TicketRepository:
    """Хранит тикеты в памяти процесса."""

    def __init__(self) -> None:
        self._tickets: dict[int, Ticket] = {}
        self._next_id = 1

    def add(self, ticket: Ticket) -> Ticket:
        raise NotImplementedError

    def get(self, ticket_id: int) -> Ticket:
        # TODO: вернуть тикет или поднять TicketNotFoundError
        raise NotImplementedError

    def list_all(self) -> list[Ticket]:
        raise NotImplementedError

    def update(self, ticket: Ticket) -> Ticket:
        raise NotImplementedError

    def delete(self, ticket_id: int) -> None:
        # TODO: удалить тикет или поднять TicketNotFoundError
        raise NotImplementedError

    def next_id(self) -> int:
        ticket_id = self._next_id
        self._next_id += 1
        return ticket_id


# --- Сервис ------------------------------------------------------------------

class TicketService:
    def __init__(self, repository: TicketRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings

    def create_ticket(self, payload: TicketCreate) -> Ticket:
        raise NotImplementedError

    def get_ticket(self, ticket_id: int) -> Ticket:
        return self._repository.get(ticket_id)

    def list_tickets(
        self,
        sort_by: str,
        order: str,
        page: int,
        page_size: int | None,
    ) -> TicketPage:
        # TODO: применить page_size из settings, если не передан,
        #  ограничить его settings.max_page_size, отсортировать список
        #  и вернуть нужную страницу
        raise NotImplementedError

    def update_ticket(self, ticket_id: int, changes: TicketUpdate) -> Ticket:
        # TODO: применить изменения, при смене статуса проверить
        # ALLOWED_TRANSITIONS и поднять InvalidStatusTransitionError
        raise NotImplementedError

    def delete_ticket(self, ticket_id: int) -> None:
        self._repository.delete(ticket_id)


# --- Зависимости --------------------------------------------------------------

_repository = TicketRepository()


def get_repository() -> TicketRepository:
    return _repository


def get_service(
    repository: TicketRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> TicketService:
    return TicketService(repository, settings)


# --- Приложение ---------------------------------------------------------------

app = FastAPI(title="HelpDesk Lite")


@app.exception_handler(TicketNotFoundError)
def handle_not_found(request: Request, exc: TicketNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})


@app.exception_handler(InvalidStatusTransitionError)
def handle_invalid_transition(request: Request, exc: InvalidStatusTransitionError) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})


@app.post(
    "/tickets",
    response_model=Ticket,
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
    summary="Создать тикет",
)
def create_ticket(payload: TicketCreate, service: TicketService = Depends(get_service)):
    raise NotImplementedError


@app.get(
    "/tickets",
    response_model=TicketPage,
    tags=["tickets"],
    summary="Получить список тикетов",
)
def list_tickets(
    sort_by: str = Query("created_at", pattern="^(created_at|priority)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int | None = Query(None, ge=1),
    service: TicketService = Depends(get_service),
):
    raise NotImplementedError


@app.get(
    "/tickets/{ticket_id}",
    response_model=Ticket,
    tags=["tickets"],
    summary="Получить тикет по id",
)
def get_ticket(ticket_id: int, service: TicketService = Depends(get_service)):
    return service.get_ticket(ticket_id)


@app.patch(
    "/tickets/{ticket_id}",
    response_model=Ticket,
    tags=["tickets"],
    summary="Изменить часть данных тикета",
)
def update_ticket(
    ticket_id: int,
    changes: TicketUpdate,
    service: TicketService = Depends(get_service),
):
    raise NotImplementedError


@app.delete(
    "/tickets/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["tickets"],
    summary="Удалить тикет",
)
def delete_ticket(ticket_id: int, service: TicketService = Depends(get_service)):
    service.delete_ticket(ticket_id)