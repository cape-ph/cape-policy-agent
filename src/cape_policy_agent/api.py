from fastapi import Request, HTTPException
from sqlmodel import Session, select
from sqlalchemy.exc import NoResultFound

from typing import List
from cape_policy_agent.app import app, engine
from cape_policy_agent.model import (
    SecurityGroup,
    PublicSecurityGroup,
    SecurityObject,
    PublicSecurityObject,
    PublicSecurityLevel,
    create_if_not_exists_token,
    create_if_not_exists_token_set,
    create_or_update_security_group,
    delete_security_group,
    create_if_not_exists_security_level,
    create_security_object,
    delete_security_object,
)


@app.exception_handler(NoResultFound)
async def no_result_found_exception_handler(request: Request, exc: NoResultFound):
    raise HTTPException(status_code=404)


@app.get("/group/{name}/ids", response_model=List[int])
async def get_group_token_ids(name: str):
    """Get the set of token ids assigned to the group.  This uniquely
    identifies the security level of the group."""
    with Session(engine) as session:
        group = session.exec(
            select(SecurityGroup).where(SecurityGroup.name == name)
        ).one()
        return list(group.ids())


@app.get("/group/{name}", response_model=PublicSecurityGroup)
async def get_group(name: str):
    """Lookup a group from the unique group name."""
    with Session(engine) as session:
        group = session.exec(
            select(SecurityGroup).where(SecurityGroup.name == name)
        ).one()

        return PublicSecurityGroup(name=group.name, tokens=list(group.values()))


@app.get("/group", response_model=List[str])
async def get_group_names(limit: int | None = None, offset: int | None = None):
    """Get the names of registered security groups."""
    with Session(engine) as session:
        if limit is not None:
            if offset is not None:
                return session.exec(
                    select(SecurityGroup.name).limit(limit).offset(offset)
                ).all()
            else:
                return session.exec(select(SecurityGroup.name).limit(limit)).all()
        else:
            return session.exec(select(SecurityGroup.name)).all()


@app.post("/group", response_model=PublicSecurityGroup)
async def create_group(group: PublicSecurityGroup):
    """Create or update a security group. This endpoint is idempotent."""
    with Session(engine) as session:
        tokens = [create_if_not_exists_token(session, t) for t in group.tokens]
        db_group = create_or_update_security_group(session, group.name, tokens)
        session.commit()
        return PublicSecurityGroup(name=db_group.name, tokens=list(db_group.values()))


@app.delete("/group/{name}", response_model=None)
async def delete_group(name: str):
    """Delete a security group."""
    with Session(engine) as session:
        group = session.exec(
            select(SecurityGroup).where(SecurityGroup.name == name)
        ).one_or_none()

        if group is not None:
            delete_security_group(session, group)
            session.commit()


@app.get("/object/{uuid}/ids", response_model=List[int])
async def get_object_token_ids(uuid: str):
    """Get the set of token ids assigned to the object.  This uniquely
    identifies the security level of the object."""
    with Session(engine) as session:
        obj = session.exec(
            select(SecurityObject).where(SecurityObject.uuid == uuid)
        ).one()

        return list(obj.level.ids())


@app.get("/object/{uuid}", response_model=PublicSecurityObject)
async def get_object(uuid: str):
    """Get the object from the universally unique identifier (UUID)."""
    with Session(engine) as session:
        obj = session.exec(
            select(SecurityObject).where(SecurityObject.uuid == uuid)
        ).one()

        return PublicSecurityObject(
            uuid=obj.uuid,
            level=PublicSecurityLevel(
                tokens=list(obj.level.values()),
                groups=[g.name for g in obj.level.groups],
            ),
        )


@app.get("/object", response_model=List[str])
async def get_object_uuids(limit: int | None = None, offset: int | None = None):
    """Get the UUIDs of registered objects."""
    with Session(engine) as session:
        if limit is not None:
            if offset is not None:
                return session.exec(
                    select(SecurityObject.uuid).limit(limit).offset(offset)
                ).all()
            else:
                return session.exec(select(SecurityObject.uuid).limit(limit)).all()
        else:
            return session.exec(select(SecurityObject.uuid)).all()


@app.post("/object", response_model=PublicSecurityObject)
async def create_object(obj: PublicSecurityObject):
    """Create or update an object.  This endpoint is idempotent."""

    def get_group_by_name(session: Session, name: str) -> SecurityGroup:
        return session.exec(
            select(SecurityGroup).where(SecurityGroup.name == name)
        ).one()

    with Session(engine) as session:
        groups = [get_group_by_name(session, name) for name in obj.level.groups]
        tokens = [
            create_if_not_exists_token(session, value) for value in obj.level.tokens
        ]
        token_set = create_if_not_exists_token_set(session, tokens)
        level = create_if_not_exists_security_level(session, token_set, groups)
        db_obj = create_security_object(session, level)
        session.flush()

        return PublicSecurityObject(
            uuid=db_obj.uuid,
            level=PublicSecurityLevel(
                tokens=list(db_obj.level.token_set.values()),
                groups=[g.name for g in db_obj.level.groups],
            ),
        )


@app.delete("/object/{uuid}", response_model=None)
async def delete_object(uuid: str):
    with Session(engine) as session:
        obj = session.exec(
            select(SecurityObject).where(SecurityObject.uuid == uuid)
        ).one_or_none()

        if obj is not None:
            delete_security_object(session, obj)
            session.commit()
