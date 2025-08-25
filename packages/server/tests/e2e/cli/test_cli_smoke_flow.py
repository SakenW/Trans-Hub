# packages/server/tests/e2e/cli/test_cli_smoke_flow.py

import pytest
from sqlalchemy import text
from trans_hub.di.container import AppContainer
from tests.helpers.factories.request_factory import create_request_data

pytestmark = pytest.mark.asyncio


@pytest.mark.e2e
async def test_smoke_flow_happy_path(
    app_container: AppContainer, migrated_db
) -> None:
    """
    Simulates a complete happy path of the CLI smoke flow by directly calling services.
    """
    # 0. Print configuration for debugging
    config = app_container.config()
    db_engine = app_container.db_engine()
    print("\n=== Configuration Debug Info ===")
    print(f"Config Type: {type(config)}")
    print(f"Config Content: {config}")
    print(f"DB Engine URL: {db_engine.url}")
    print(f"DB Engine Type: {type(db_engine)}")
    
    # 检查实际使用的数据库引擎URL
    async with app_container.db_sessionmaker()() as session:
        actual_engine_url = str(session.bind.url)
        print(f"Actual Engine URL: {actual_engine_url}")
        
        try:
            result = await session.execute(
                text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'th' AND table_name = 'projects')")
            )
            table_exists = result.scalar()
            print(f"\nth.projects table exists: {table_exists}")
            
            if not table_exists:
                # 列出 th schema 下的所有表
                result = await session.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'th' ORDER BY table_name")
                )
                tables = result.fetchall()
                print(f"Tables in 'th' schema: {[row[0] for row in tables]}")
        except Exception as e:
            print(f"Error checking table existence: {e}")
    
    print("=== End Configuration Debug ===")
    
    # 1. Get services from the container
    request_service = app_container.request_translation_service()
    query_service = app_container.translation_query_service()

    # 2. Create test data using the factory
    request_data = create_request_data(
        keys={"id": "test-key-001"},
        source_payload={"text": "Hello, world!"},
        target_langs=["zh-Hans"]
    )

    # 3. Submit a new translation request
    content_id = await request_service.execute(**request_data)
    assert content_id is not None

    # 4. Query the translation result
    result = await query_service.execute(
        project_id=request_data["project_id"],
        namespace=request_data["namespace"],
        keys=request_data["keys"],
        target_lang="zh-Hans"
    )
    # The result might be None if no translation is available yet,
    # but the query should not raise an error
    assert result is None or isinstance(result, dict)
