import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SKILLPROOF_INTEGRATION") != "1",
    reason="set SKILLPROOF_INTEGRATION=1 to test Postgres, Redis, and Neo4j",
)


def test_postgres_accepts_a_query() -> None:
    import psycopg

    with psycopg.connect(os.environ["STACK_DATABASE_URL"]) as connection:
        row = connection.execute("SELECT 1").fetchone()
    assert row is not None
    assert row[0] == 1


def test_redis_answers_ping() -> None:
    import redis

    client = redis.Redis.from_url(os.environ["STACK_REDIS_URL"], socket_connect_timeout=2)
    assert client.ping() is True


def test_neo4j_answers_a_read_query() -> None:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        os.environ["STACK_NEO4J_URI"],
        auth=(os.environ["STACK_NEO4J_USER"], os.environ["STACK_NEO4J_PASSWORD"]),
    )
    try:
        with driver.session() as session:
            row = session.run("RETURN 1 AS n").single()
        assert row is not None
        assert row["n"] == 1
    finally:
        driver.close()
