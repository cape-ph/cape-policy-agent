# Note: need to import API so it's served
import cape_policy_agent.api  # type: ignore # noqa: F401

from cape_policy_agent.app import app, host, port

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=host, port=port)
