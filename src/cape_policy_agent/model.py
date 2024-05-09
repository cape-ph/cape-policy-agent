from functools import reduce
from typing import FrozenSet, Iterable, List
from uuid import uuid4

from sqlalchemy import Column, String, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Relationship, Session, SQLModel, delete, select  # type: ignore


class TokenTokenSet(SQLModel, table=True):
    token_id: int = Field(foreign_key="token.id", primary_key=True)
    token_set_id: int = Field(foreign_key="tokenset.id", primary_key=True)


class Token(SQLModel, table=True):
    """A type for tokens.

    Note:
        Tokens are simple labels that are used to annotate data and have no
        special meaning other than whatever semantic meaning the system
        designer assigns to them.
    """

    id: int | None = Field(default=None, primary_key=True)
    value: str = Field(sa_column=Column("value", String, unique=True))


def _as_int(value: int | None) -> int:
    if value is None:
        raise ValueError("missing value")
    return value


def create_if_not_exists_token(session: Session, value: str) -> Token:
    """Create a token if it does not already exist

    Args:
        session (Session): the database session
        value (str): the token value

    Returns:
        Token: the token corresponding to the value.  This is either
            a new token (if the token isn't already in the database)
            or an existing token.
    """
    token = session.exec(select(Token).where(Token.value == value)).one_or_none()

    if token is None:
        token = Token(value=value)
        session.add(token)
        session.flush()
    return token


class TokenSet(SQLModel, table=True):
    """A type for a set of tokens."""

    id: int | None = Field(default=None, primary_key=True)
    tokens: List[Token] = Relationship(link_model=TokenTokenSet)
    levels: List["SecurityLevel"] = Relationship(back_populates="token_set")
    groups: List["SecurityGroup"] = Relationship(back_populates="token_set")

    def __str__(self) -> str:
        return "{" + ", ".join([t.value for t in self.tokens]) + "}"

    def ids(self) -> FrozenSet[int]:
        """Get a frozenset of the token ids

        Raises:
            TypeError: raised if the token has no id

        Return:
            FrozenSet[int]: the set of token ids
        """
        return frozenset(_as_int(t.id) for t in self.tokens)

    def values(self) -> FrozenSet[str]:
        """Get a frozenset of the token values

        Return:
            FrozenSet[str]: the set of token values
        """
        return frozenset(t.value for t in self.tokens)


def create_token_set(session: Session, tokens: Iterable[Token]) -> TokenSet:
    """Create a new token set and add it to a database session

    Args:
        session (Session): the database session
        tokens (Iterable[Token]): the tokens that are contained in the set

    Return:
        TokenSet: the token set
    """
    token_set = TokenSet()
    session.add(token_set)
    session.flush()

    for token in tokens:
        link = TokenTokenSet(
            token_id=_as_int(token.id), token_set_id=_as_int(token_set.id)
        )
        session.add(link)

    session.flush()
    return token_set


def create_if_not_exists_token_set(
    session: Session, tokens: Iterable[Token]
) -> TokenSet:
    """Create a token if it does not exist

    Args:
        session (Session): the database session
        tokens (Iterable[Token]): the tokens that are contained in the set

    Returns:
        TokenSet: the token set
    """
    token_ids = ",".join([str(s) for s in sorted([_as_int(t.id) for t in tokens])])
    token_set = session.exec(
        select(TokenSet)
        .join(TokenTokenSet)
        .group_by(TokenTokenSet.token_set_id)  # type: ignore
        .having(func.aggregate_strings(TokenTokenSet.token_id, ",") == token_ids)  # type: ignore
    ).one_or_none()

    if token_set is None:
        token_set = create_token_set(session, tokens)
    return token_set


def update_token_set(
    session: Session, token_set: TokenSet, tokens: Iterable[Token]
) -> TokenSet:
    """Update a token set to contain the tokens

    Args:
        session (Session): the database session
        token_set (TokenSet): the token set
        tokens (Iterable[Token]): the tokens that are to be contained in the set

    Returns:
        TokenSet: the updated token set
    """
    if token_set.id is None:
        raise ValueError("missing value")

    links = session.exec(
        select(TokenTokenSet).where(TokenTokenSet.token_set_id == token_set.id)
    ).fetchall()

    # Delete old links that are no longer being used
    token_ids = [_as_int(tok.id) for tok in tokens]
    for link in links:
        if link.token_id not in token_ids:
            session.delete(link)

    # Add new links that aren't already there
    token_ids = [link.token_id for link in links]
    for token in tokens:
        if token.id is None:
            raise ValueError("missing value")

        if token.id not in token_ids:
            link = TokenTokenSet(token_id=token.id, token_set_id=token_set.id)
            session.add(link)

    session.flush()
    return token_set


def delete_token_set(session: Session, token_set: TokenSet) -> TokenSet:
    """Delete a token set

    Args:
        session (Session): the database session
        token_set (TokenSet): the token set

    Returns:
        TokenSet: the token set that has been deleted from the database
    """
    if token_set.id is None:
        raise ValueError("missing value")

    # Note: typehints in sqlmodel are broken here ...
    query = delete(TokenTokenSet).where(TokenTokenSet.token_set_id == token_set.id)  # type: ignore
    session.exec(query)  # type: ignore
    session.delete(token_set)
    session.flush()
    return token_set


class SecurityGroup(SQLModel, table=True):
    """A type for a security group."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column("name", String, unique=True))
    token_set_id: int | None = Field(foreign_key="tokenset.id")
    token_set: TokenSet | None = Relationship(back_populates="groups")

    def ids(self) -> FrozenSet[int]:
        return self.token_set.ids() if self.token_set else frozenset()

    def values(self) -> FrozenSet[str]:
        return self.token_set.values() if self.token_set else frozenset()


def create_or_update_security_group(
    session: Session, name: str, tokens: Iterable[Token]
) -> SecurityGroup:
    """Create a security group

    Args:
        session (Session): the database session
        name (str): the security group name
        tokens (Iterable[Token]): the security group tokens

    Returns:
        SecurityGroup: the security group
    """
    group = session.exec(
        select(SecurityGroup).where(SecurityGroup.name == name)
    ).one_or_none()

    if group is None:
        token_set = TokenSet()
        group = SecurityGroup(name=name, token_set_id=token_set.id)
        session.add(token_set)
        session.add(group)
        session.flush()
    else:
        if group.token_set is None:
            raise ValueError("missing value")
        token_set = group.token_set

    update_token_set(session, token_set, tokens)
    return group


def delete_security_group(session: Session, group: SecurityGroup) -> SecurityGroup:
    """Delete a security group

    Args:
        session (Session): the database session
        group (SecurityGroup): the security group

    Returns:
        SecurityGroup: the security group deleted from the database
    """
    if group.token_set:
        delete_token_set(session, group.token_set)
    session.delete(group)
    session.flush()
    return group


class PublicSecurityGroup(SQLModel):
    name: str
    tokens: List[str]


class SecurityLevelSecurityGroup(SQLModel, table=True):
    security_level_id: int = Field(foreign_key="securitylevel.id", primary_key=True)
    security_group_id: int = Field(foreign_key="securitygroup.id", primary_key=True)


class SecurityLevel(SQLModel, table=True):
    """A type for a security level."""

    id: int | None = Field(default=None, primary_key=True)
    token_set_id: int = Field(foreign_key="tokenset.id")
    token_set: TokenSet = Relationship(back_populates="levels")
    groups: List[SecurityGroup] = Relationship(link_model=SecurityLevelSecurityGroup)
    objects: List["SecurityObject"] = Relationship(back_populates="level")

    def __str__(self) -> str:
        ind = str(self.token_set)
        groups = "{" + ", ".join([str(g.token_set) for g in self.groups]) + "}"
        return f"SecurityLevel({ind}, {groups})"

    def ids(self) -> FrozenSet[int]:
        tokens: FrozenSet[int] = self.token_set.ids() if self.token_set else frozenset()
        components = [tokens] + [g.ids() for g in self.groups]
        return reduce(lambda a, b: a.union(b), components)

    def values(self) -> FrozenSet[str]:
        tokens: FrozenSet[str] = (
            self.token_set.values() if self.token_set else frozenset()
        )
        components = [tokens] + [g.values() for g in self.groups]
        return reduce(lambda a, b: a.union(b), components)


def create_if_not_exists_security_level(
    session: Session, token_set: TokenSet, groups: Iterable[SecurityGroup]
) -> SecurityLevel:
    """Create a security level if it does not already exist

    Args:
        session (Session): the database session
        token_set (TokenSet): the individual controls
        groups (Iterable[SecurityGroup]): the group controls

    Return:
        SecurityLevel: the security level corresponding to token_set and
            groups. This is either a new security level or an existing security
            level.
    """
    group_ids = ",".join([str(s) for s in sorted([_as_int(g.id) for g in groups])])
    level = session.exec(
        select(SecurityLevel)
        .join(SecurityLevelSecurityGroup)
        .group_by(SecurityLevelSecurityGroup.security_level_id)  # type: ignore
        .having(
            func.aggregate_strings(SecurityLevelSecurityGroup.security_group_id, ",")  # type: ignore
            == group_ids
        )
    ).one_or_none()

    if level is None:
        level = SecurityLevel(token_set_id=_as_int(token_set.id))
        session.add(level)
        session.flush()

        for group in groups:
            link = SecurityLevelSecurityGroup(
                security_level_id=_as_int(level.id), security_group_id=_as_int(group.id)
            )
            session.add(link)
        session.flush()

    return level


def delete_security_level(session: Session, level: SecurityLevel) -> SecurityLevel:
    """Delete a security level

    Args:
        session (Session): the database session
        level (SecurityLevel): the security level

    Returns:
        SecurityLevel: the security level deleted from the database
    """
    if level.id is None:
        raise ValueError("missing value")

    if level.token_set:
        delete_token_set(session, level.token_set)

    # Note: sqlmodel typehints are broken here ...
    query = delete(SecurityLevelSecurityGroup).where(
        SecurityLevelSecurityGroup.security_level_id == level.id  # type: ignore
    )
    session.exec(query)  # type: ignore
    session.flush()
    return level


class PublicSecurityLevel(SQLModel):
    tokens: List[str]
    groups: List[str]


class SecurityObject(SQLModel, table=True):
    """A class for abstract objects that are assigned a security label."""

    id: int | None = Field(default=None, primary_key=True)
    uuid: str = Field(sa_column=Column("uuid", String, unique=True))
    level_id: int = Field(foreign_key="securitylevel.id")
    level: SecurityLevel = Relationship(back_populates="objects")


class PublicSecurityObject(SQLModel):
    uuid: str
    level: PublicSecurityLevel


def create_security_object(
    session: Session, level: SecurityLevel, uuid: str | None = None
) -> SecurityObject:
    """Create a security object

    Args:
        session (Session): the database session
        level (SecurityLevel): the security level of the object
        uuid (str | None, optional): the object UUID. If not provided, this
            function generates a unique UUID for you. Defaults to None.

    Returns:
        SecurityObject: the security object
    """
    if uuid is None:
        uuid = str(uuid4())
    obj = SecurityObject(uuid=uuid, level_id=_as_int(level.id))

    try:
        session.add(obj)
        session.flush()
    except IntegrityError:
        # Generate a new UUID until we don't have a collision
        return create_security_object(session, level, None)

    return obj


def delete_security_object(session: Session, obj: SecurityObject) -> SecurityObject:
    """Delete a security object

    Args:
        session (Session): the database session
        obj (SecurityObject): the security object

    Returns:
        SecurityObject: the security object deleted from the database
    """
    session.delete(obj)
    session.flush()
    return obj
