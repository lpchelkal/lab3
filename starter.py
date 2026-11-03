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


class TicketDeleted(BaseModel):
    detail: str


# --- Репозиторий --------------------------------------------------------------

class TicketRepository:
    """Хранит тикеты в памяти процесса."""

    def __init__(self) -> None:
        self._tickets: dict[int, Ticket] = {}
        self._next_id = 1

    def add(self, ticket: Ticket) -> Ticket:
        self._tickets[ticket.id] = ticket
        return ticket

    def get(self, ticket_id: int) -> Ticket:
        # TODO: вернуть тикет или поднять TicketNotFoundError
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    def list_all(self) -> list[Ticket]:
        return list(self._tickets.values())

    def update(self, ticket: Ticket) -> Ticket:
        self._tickets[ticket.id] = ticket
        return ticket

    def delete(self, ticket_id: int) -> None:
        # TODO: удалить тикет или поднять TicketNotFoundError
        if ticket_id not in self._tickets:
            raise TicketNotFoundError(ticket_id)
        del self._tickets[ticket_id]

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
        ticket = Ticket(
            id=self._repository.next_id(),
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            status=TicketStatus.open,
            assignee=payload.assignee,
            created_at=datetime.now()
        )
        return self._repository.add(ticket)

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
        settings = get_settings()
        ps = min(page_size, settings.max_page_size) if page_size is not None else settings.default_page_size
        priority_order:dict[Priority, int] = {Priority.low: 0, Priority.normal: 1, Priority.high: 2, Priority.urgent: 3}
        resl: list[Ticket] = self._repository.list_all()
        if sort_by=="priority":
            resl.sort(key=lambda t: priority_order[t.priority], reverse=(order=="desc"))
        else:
            resl.sort(key=lambda t: t.created_at, reverse=(order=="desc"))
        total = len(resl)
        resl = resl[(page-1)*ps: (page-1)*ps+ps]
        res: TicketPage = TicketPage(items=resl, total=total, page=page, page_size=ps)
        return res

    def update_ticket(self, ticket_id: int, changes: TicketUpdate) -> Ticket:
        # TODO: применить изменения, при смене статуса проверить
        # ALLOWED_TRANSITIONS и поднять InvalidStatusTransitionError
        ticket = self._repository.get(ticket_id)
        updates = changes.model_dump(exclude_unset=True)

        new_status = updates.get("status")
        if (
            new_status is not None and new_status not in ALLOWED_TRANSITIONS[ticket.status]
        ):
            raise InvalidStatusTransitionError(ticket.status, new_status)

        updated = ticket.model_copy(update=updates)
        return self._repository.update(updated)

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
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": str(exc)})


@app.post(
    "/tickets",
    response_model=Ticket,
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
    summary="Создать тикет",
)
def create_ticket(payload: TicketCreate, service: TicketService = Depends(get_service)):
    return service.create_ticket(payload)


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
    return service.list_tickets(sort_by, order, page, page_size)


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
    return service.update_ticket(ticket_id, changes)


@app.delete(
    "/tickets/{ticket_id}",
    response_model=TicketDeleted,
    status_code=status.HTTP_200_OK,
    tags=["tickets"],
    summary="Удалить тикет",
)
def delete_ticket(ticket_id: int, service: TicketService = Depends(get_service)):
    service.delete_ticket(ticket_id)
    return TicketDeleted(detail=f"Тикет {ticket_id} удалён")