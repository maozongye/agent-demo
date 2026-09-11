"""This file contains the database service for the application."""

from typing import (
    List,
    Optional,
)

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool
from sqlmodel import (
    Session,
    SQLModel,
    create_engine,
    select,
)

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger
from app.models.data_report import DataReport
from app.models.email_audit import EmailAuditLog
from app.models.email_draft import EmailDraft, EmailStatus
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.session import Session as ChatSession
from app.models.tenant import MembershipRole, Tenant, TenantMembership, TenantStatus
from app.models.user import User
from app.schemas.chat import Message as PydanticMessage


class DatabaseService:
    """Service class for database operations.

    This class handles all database operations for Users, Sessions, and Messages.
    It uses SQLModel for ORM operations and maintains a connection pool.
    """

    def __init__(self):
        """Initialize database service with connection pool."""
        try:
            # Configure environment-specific database connection pool settings
            pool_size = settings.POSTGRES_POOL_SIZE
            max_overflow = settings.POSTGRES_MAX_OVERFLOW

            # Create engine with appropriate pool configuration
            self.engine = create_engine(
                settings.POSTGRES_URL,
                pool_pre_ping=True,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=30,  # Connection timeout (seconds)
                pool_recycle=1800,  # Recycle connections after 30 minutes
            )

            # Create tables (only if they don't exist)
            SQLModel.metadata.create_all(self.engine)

            logger.info(
                "database_initialized",
                environment=settings.ENVIRONMENT.value,
                pool_size=pool_size,
                max_overflow=max_overflow,
            )
        except Exception as e:
            # Include OperationalError and other connect failures so unit tests can run without Postgres.
            logger.error("database_initialization_error", error=str(e), environment=settings.ENVIRONMENT.value)
            self.engine = None
            if settings.ENVIRONMENT not in (Environment.PRODUCTION, Environment.TEST):
                raise

    async def create_user(self, email: str, password: str) -> User:
        """Create a new user.

        Args:
            email: User's email address
            password: Hashed password

        Returns:
            User: The created user
        """
        with Session(self.engine) as session:
            user = User(email=email, hashed_password=password)
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("user_created", email=email)
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: The ID of the user to retrieve

        Returns:
            Optional[User]: The user if found, None otherwise
        """
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            return user

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email.

        Args:
            email: The email of the user to retrieve

        Returns:
            Optional[User]: The user if found, None otherwise
        """
        with Session(self.engine) as session:
            statement = select(User).where(User.email == email)
            user = session.exec(statement).first()
            return user

    async def delete_user_by_email(self, email: str) -> bool:
        """Delete a user by email.

        Args:
            email: The email of the user to delete

        Returns:
            bool: True if deletion was successful, False if user not found
        """
        with Session(self.engine) as session:
            user = session.exec(select(User).where(User.email == email)).first()
            if not user:
                return False

            session.delete(user)
            session.commit()
            logger.info("user_deleted", email=email)
            return True

    async def create_session(
        self, session_id: str, user_id: int, name: str = "", tenant_id: Optional[int] = None
    ) -> ChatSession:
        """Create a new chat session.

        Args:
            session_id: The ID for the new session
            user_id: The ID of the user who owns the session
            name: Optional name for the session (defaults to empty string)
            tenant_id: Optional tenant for isolation (required for new multi-tenant sessions)

        Returns:
            ChatSession: The created session
        """
        with Session(self.engine) as session:
            chat_session = ChatSession(id=session_id, user_id=user_id, name=name, tenant_id=tenant_id)
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("session_created", session_id=session_id, user_id=user_id, tenant_id=tenant_id, name=name)
            return chat_session

    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get a session by ID.

        Args:
            session_id: The ID of the session to retrieve

        Returns:
            Optional[ChatSession]: The session if found, None otherwise
        """
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            return chat_session

    async def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        """Get all sessions for a user.

        Args:
            user_id: The ID of the user

        Returns:
            List[ChatSession]: List of user's sessions
        """
        with Session(self.engine) as session:
            statement = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at)
            sessions = session.exec(statement).all()
            return sessions

    async def update_session_name(self, session_id: str, name: str) -> ChatSession:
        """Update a session's name.

        Args:
            session_id: The ID of the session to update
            name: The new name for the session

        Returns:
            ChatSession: The updated session

        Raises:
            HTTPException: If session is not found
        """
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if not chat_session:
                raise HTTPException(status_code=404, detail="Session not found")

            chat_session.name = name
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("session_name_updated", session_id=session_id, name=name)
            return chat_session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: The ID of the session to delete

        Returns:
            bool: True if deletion was successful

        Raises:
            HTTPException: If there's an error deleting the session
        """
        try:
            with Session(self.engine) as session:
                chat_session = session.get(ChatSession, session_id)
                if not chat_session:
                    return False
                session.delete(chat_session)
                session.commit()
                logger.info("session_deleted", session_id=session_id)
                return True
        except Exception as e:
            logger.error("error_deleting_session", session_id=session_id, error=e)
            raise HTTPException(status_code=500, detail="Error deleting session")

    async def get_messages_by_session_id(self, session_id: str) -> List[Message]:
        """Get all messages by session ID.

        Args:
            session_id: The ID of the session

        Returns:
            List[Message]: List of messages in the session
        """
        with Session(self.engine) as session:
            statement = select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
            messages = session.exec(statement).all()
            return messages

    async def save_messages(self, messages: List[PydanticMessage], session_id: str) -> List[Message]:
        """Save a message to the database.

        Args:
            messages: The messages to save
            session_id: The ID of the session
        """
        with Session(self.engine) as session:
            messages = [
                Message(session_id=session_id, role=message.role, content=message.content) for message in messages
            ]
            session.add_all(messages)
            session.commit()
            session.refresh_all(messages)
            logger.info("messages_saved", session_id=session_id, role=messages[0].role)
            return messages

    def get_session_maker(self):
        """Get a session maker for creating database sessions.

        Returns:
            Session: A SQLModel session maker
        """
        return Session(self.engine)

    async def health_check(self) -> bool:
        """Check database connection health.

        Returns:
            bool: True if database is healthy, False otherwise
        """
        try:
            with Session(self.engine) as session:
                # Execute a simple query to check connection
                session.exec(select(1)).first()
                return True
        except Exception as e:
            logger.error("database_health_check_failed", error=str(e))
            return False

    async def create_tenant(self, name: str, slug: str, status: str = TenantStatus.ACTIVE.value) -> Tenant:
        """Create a tenant.

        Args:
            name: Display name.
            slug: Unique slug.
            status: Tenant status.

        Returns:
            Tenant: Created tenant.
        """
        with Session(self.engine) as session:
            tenant = Tenant(name=name, slug=slug, status=status)
            session.add(tenant)
            session.commit()
            session.refresh(tenant)
            logger.info("tenant_created", tenant_id=tenant.id, slug=slug)
            return tenant

    async def get_tenant(self, tenant_id: int) -> Optional[Tenant]:
        """Get a tenant by id."""
        with Session(self.engine) as session:
            return session.get(Tenant, tenant_id)

    async def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get a tenant by slug."""
        with Session(self.engine) as session:
            return session.exec(select(Tenant).where(Tenant.slug == slug)).first()

    async def create_membership(
        self, user_id: int, tenant_id: int, role: str = MembershipRole.OWNER.value
    ) -> TenantMembership:
        """Create a tenant membership."""
        with Session(self.engine) as session:
            membership = TenantMembership(user_id=user_id, tenant_id=tenant_id, role=role)
            session.add(membership)
            session.commit()
            session.refresh(membership)
            logger.info("membership_created", user_id=user_id, tenant_id=tenant_id, role=role)
            return membership

    async def get_membership(self, user_id: int, tenant_id: int) -> Optional[TenantMembership]:
        """Return membership if user belongs to tenant."""
        with Session(self.engine) as session:
            statement = select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
            return session.exec(statement).first()

    async def list_memberships_for_user(self, user_id: int) -> List[TenantMembership]:
        """List all memberships for a user."""
        with Session(self.engine) as session:
            statement = select(TenantMembership).where(TenantMembership.user_id == user_id)
            return list(session.exec(statement).all())

    async def get_default_tenant_id_for_user(self, user_id: int) -> Optional[int]:
        """Return the first (typically personal) tenant id for a user."""
        memberships = await self.list_memberships_for_user(user_id)
        if not memberships:
            return None
        return memberships[0].tenant_id

    async def create_email_draft(
        self,
        tenant_id: int,
        subject: str,
        body: str,
        to_address: str,
        *,
        category: str = "",
        category_confidence: float = 0.0,
        inbound_from: str = "",
        inbound_subject: str = "",
        inbound_body: str = "",
    ) -> EmailDraft:
        """Persist a new email draft in draft status."""
        with Session(self.engine) as session:
            draft = EmailDraft(
                tenant_id=tenant_id,
                status=EmailStatus.DRAFT.value,
                subject=subject,
                body=body,
                to_address=to_address,
                category=category,
                category_confidence=category_confidence,
                inbound_from=inbound_from,
                inbound_subject=inbound_subject,
                inbound_body=inbound_body,
            )
            session.add(draft)
            session.commit()
            session.refresh(draft)
            logger.info("email_draft_created", draft_id=draft.id, tenant_id=tenant_id)
            return draft

    async def get_email_draft(self, draft_id: int, tenant_id: int) -> Optional[EmailDraft]:
        """Get an email draft scoped to a tenant."""
        with Session(self.engine) as session:
            draft = session.get(EmailDraft, draft_id)
            if draft is None or draft.tenant_id != tenant_id:
                return None
            return draft

    async def save_email_draft(self, draft: EmailDraft) -> EmailDraft:
        """Persist updates to an email draft."""
        with Session(self.engine) as session:
            merged = session.merge(draft)
            session.commit()
            session.refresh(merged)
            return merged


    async def add_email_audit(
        self,
        *,
        tenant_id: int,
        draft_id: int,
        actor_user_id: int,
        action: str,
        detail: str = "",
    ) -> EmailAuditLog:
        """Append an email audit log row."""
        with Session(self.engine) as session:
            row = EmailAuditLog(
                tenant_id=tenant_id,
                draft_id=draft_id,
                actor_user_id=actor_user_id,
                action=action,
                detail=detail,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    async def list_email_audits(self, tenant_id: int, draft_id: int) -> list[EmailAuditLog]:
        """List audit rows for a draft in a tenant."""
        with Session(self.engine) as session:
            stmt = select(EmailAuditLog).where(
                EmailAuditLog.tenant_id == tenant_id,
                EmailAuditLog.draft_id == draft_id,
            )
            return list(session.exec(stmt).all())

    async def create_data_report(
        self,
        *,
        tenant_id: int,
        created_by: int,
        query_text: str,
        sql_text: str,
        rows_json: str,
        report_text: str,
        status: str = "completed",
    ) -> DataReport:
        with Session(self.engine) as session:
            row = DataReport(
                tenant_id=tenant_id,
                created_by=created_by,
                query_text=query_text,
                sql_text=sql_text,
                rows_json=rows_json,
                report_text=report_text,
                status=status,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    async def get_data_report(self, tenant_id: int, report_id: int) -> Optional[DataReport]:
        with Session(self.engine) as session:
            row = session.get(DataReport, report_id)
            if row is None or row.tenant_id != tenant_id:
                return None
            return row


# Create a singleton instance
database_service = DatabaseService()
