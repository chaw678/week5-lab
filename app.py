"""QuackLoan: a rubber-duck lending library prototype.

Run with:  python3 app.py
"""

from datetime import datetime, timedelta

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from sqlalchemy import DateTime, ForeignKey, Index, String, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

LOAN_PERIOD = timedelta(days=7)


class Base(DeclarativeBase):
    pass


class Member(Base):
    __tablename__ = "member"

    member_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)

    loans: Mapped[list["Loan"]] = relationship(back_populates="member")


class Duck(Base):
    __tablename__ = "duck"

    duck_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)

    loans: Mapped[list["Loan"]] = relationship(back_populates="duck")

    @property
    def current_loan(self):
        """The loan that has not been returned yet, if any."""
        return next((loan for loan in self.loans if loan.returned_at is None), None)


class Loan(Base):
    __tablename__ = "loan"
    # Database-level guarantee that a duck has at most one current loan.
    __table_args__ = (
        Index(
            "one_current_loan_per_duck",
            "duck_id",
            unique=True,
            sqlite_where=text("returned_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("member.member_id"))
    duck_id: Mapped[str] = mapped_column(ForeignKey("duck.duck_id"))
    borrowed_at: Mapped[datetime] = mapped_column(DateTime)
    due_at: Mapped[datetime] = mapped_column(DateTime)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    member: Mapped[Member] = relationship(back_populates="loans")
    duck: Mapped[Duck] = relationship(back_populates="loans")


class DuckUnavailable(Exception):
    pass


def borrow_duck(session, member, duck, now=None):
    """Create a 7-day loan of `duck` to `member`, or raise DuckUnavailable."""
    if duck.current_loan is not None:
        raise DuckUnavailable(duck.name)

    now = now or datetime.now()
    loan = Loan(member=member, duck=duck, borrowed_at=now, due_at=now + LOAN_PERIOD)
    session.add(loan)
    try:
        session.commit()
    except IntegrityError:
        # Someone else borrowed the duck between our check and our insert.
        session.rollback()
        raise DuckUnavailable(duck.name)
    return loan


def seed(session):
    session.add_all(
        [
            Member(member_id="M001", name="Ada Tan", email="ada@example.edu"),
            Member(member_id="M002", name="Ben Lim", email="ben@example.edu"),
            Member(member_id="M003", name="Chen Wei", email="chen@example.edu"),
            Duck(duck_id="D001", name="Sir Quacksalot"),
            Duck(duck_id="D002", name="Null Pointer"),
            Duck(duck_id="D003", name="Stack Overflow"),
            Duck(duck_id="D004", name="Captain Segfault"),
        ]
    )
    session.commit()


def create_app():
    app = Flask(__name__)
    app.secret_key = "dev-only"  # only used to sign flash messages

    # StaticPool keeps one connection open so the in-memory database survives
    # between requests.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    app.Session = Session
    app.engine = engine

    with Session() as session:
        seed(session)

    @app.get("/")
    def index():
        with Session() as session:
            ducks = session.scalars(select(Duck).order_by(Duck.duck_id)).all()
            members = session.scalars(select(Member).order_by(Member.name)).all()
            return render_template("index.html", ducks=ducks, members=members)

    @app.post("/loans")
    def create_loan():
        with Session() as session:
            member = session.get(Member, request.form.get("member_id", ""))
            duck = session.get(Duck, request.form.get("duck_id", ""))
            if member is None or duck is None:
                abort(400, "Unknown member or duck.")

            try:
                loan = borrow_duck(session, member, duck)
            except DuckUnavailable:
                flash(f"Sorry, {duck.name} is unavailable: it is already on loan.", "error")
            else:
                flash(
                    f"{member.name} borrowed {duck.name}. "
                    f"Due back {loan.due_at:%a %d %b %Y, %H:%M}.",
                    "success",
                )
        return redirect(url_for("index"))

    return app


if __name__ == "__main__":
    # Single-threaded so requests never share the one database connection.
    create_app().run(debug=True, threaded=False)
