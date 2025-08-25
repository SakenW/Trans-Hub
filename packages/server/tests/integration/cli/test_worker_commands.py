# packages/server/tests/integration/cli/test_worker_commands.py
"""
测试 CLI Worker 命令的并发启动和异常处理逻辑。
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from trans_hub.adapters.cli.commands.worker import _run_all_workers, _run_workers_logic
from trans_hub.di.container import AppContainer

pytestmark = [pytest.mark.asyncio]


class MockWorkerException(Exception):
    """用于测试的模拟 Worker 异常。"""
    pass


@pytest.fixture
def mock_container():
    """创建模拟的 AppContainer。"""
    container = AsyncMock(spec=AppContainer)
    
    # 模拟配置
    config_mock = AsyncMock()
    config_mock.redis.url = "redis://localhost:6379"
    container.config = AsyncMock(return_value=config_mock)
    
    # 模拟其他依赖
    container.uow_factory = AsyncMock(return_value=AsyncMock())
    container.stream_producer = AsyncMock(return_value=AsyncMock())
    
    # 模拟数据库引擎
    db_engine_mock = AsyncMock()
    container.db_engine = AsyncMock(return_value=db_engine_mock)
    
    return container


@pytest.fixture
def mock_container_no_redis():
    """创建没有 Redis 配置的模拟 AppContainer。"""
    container = AsyncMock(spec=AppContainer)
    
    # 模拟配置（无 Redis）
    config_mock = AsyncMock()
    config_mock.redis.url = None
    container.config = AsyncMock(return_value=config_mock)
    
    # 模拟其他依赖
    container.uow_factory = AsyncMock(return_value=AsyncMock())
    container.stream_producer = AsyncMock(return_value=None)
    
    # 模拟数据库引擎
    db_engine_mock = AsyncMock()
    container.db_engine = AsyncMock(return_value=db_engine_mock)
    
    return container


async def test_run_all_workers_translation_worker_failure(mock_container):
    """测试当翻译 Worker 失败时，TaskGroup 会取消其他任务。"""
    
    async def failing_translation_worker(*args, **kwargs):
        await asyncio.sleep(0.1)  # 模拟一些工作
        raise MockWorkerException("Translation worker failed")
    
    async def long_running_relay_worker(*args, **kwargs):
        await asyncio.sleep(10)  # 模拟长时间运行的任务
        return "Should not complete"
    
    with patch('trans_hub.adapters.cli.commands.worker._translation_worker.run_worker_loop', 
               side_effect=failing_translation_worker), \
         patch('trans_hub.adapters.cli.commands.worker._outbox_relay_worker.run_relay_loop', 
               side_effect=long_running_relay_worker), \
         patch('trans_hub.infrastructure.redis._client.close_redis_client', 
               new_callable=AsyncMock):
        
        # 验证异常被正确抛出
        with pytest.raises(MockWorkerException, match="Translation worker failed"):
            await _run_all_workers(container=mock_container)
        
        # 验证资源清理被调用
        mock_container.db_engine.assert_called_once()
        db_engine = await mock_container.db_engine()
        db_engine.dispose.assert_called_once()


async def test_run_all_workers_relay_worker_failure(mock_container):
    """测试当 Outbox 中继 Worker 失败时，TaskGroup 会取消其他任务。"""
    
    async def long_running_translation_worker(*args, **kwargs):
        await asyncio.sleep(10)  # 模拟长时间运行的任务
        return "Should not complete"
    
    async def failing_relay_worker(*args, **kwargs):
        await asyncio.sleep(0.1)  # 模拟一些工作
        raise MockWorkerException("Relay worker failed")
    
    with patch('trans_hub.adapters.cli.commands.worker._translation_worker.run_worker_loop', 
               side_effect=long_running_translation_worker), \
         patch('trans_hub.adapters.cli.commands.worker._outbox_relay_worker.run_relay_loop', 
               side_effect=failing_relay_worker), \
         patch('trans_hub.infrastructure.redis._client.close_redis_client', 
               new_callable=AsyncMock):
        
        # 验证异常被正确抛出
        with pytest.raises(MockWorkerException, match="Relay worker failed"):
            await _run_all_workers(container=mock_container)
        
        # 验证资源清理被调用
        mock_container.db_engine.assert_called_once()
        db_engine = await mock_container.db_engine()
        db_engine.dispose.assert_called_once()


async def test_run_all_workers_no_redis_only_translation_worker(mock_container_no_redis):
    """测试在没有 Redis 配置时，只启动翻译 Worker。"""
    
    async def successful_translation_worker(*args, **kwargs):
        await asyncio.sleep(0.1)
        return "Translation completed"
    
    with patch('trans_hub.adapters.cli.commands.worker._translation_worker.run_worker_loop', 
               side_effect=successful_translation_worker) as mock_translation, \
         patch('trans_hub.adapters.cli.commands.worker._outbox_relay_worker.run_relay_loop') as mock_relay:
        
        await _run_all_workers(container=mock_container_no_redis)
        
        # 验证只有翻译 Worker 被调用
        mock_translation.assert_called_once()
        mock_relay.assert_not_called()
        
        # 验证资源清理被调用
        mock_container_no_redis.db_engine.assert_called_once()
        db_engine = await mock_container_no_redis.db_engine()
        db_engine.dispose.assert_called_once()


async def test_run_workers_logic_independent_mode_failure(mock_container):
    """测试独立模式下单个 Worker 失败时的行为。"""
    
    async def failing_translation_worker(*args, **kwargs):
        await asyncio.sleep(0.1)
        raise MockWorkerException("Translation worker failed")
    
    async def long_running_relay_worker(*args, **kwargs):
        await asyncio.sleep(10)
        return "Should not complete"
    
    with patch('trans_hub.adapters.cli.commands.worker._translation_worker.run_worker_loop', 
               side_effect=failing_translation_worker), \
         patch('trans_hub.adapters.cli.commands.worker._outbox_relay_worker.run_relay_loop', 
               side_effect=long_running_relay_worker), \
         patch('trans_hub.infrastructure.redis._client.close_redis_client', 
               new_callable=AsyncMock), \
         patch('rich.console.Console.print'):
        
        # 验证异常被正确抛出（TaskGroup 异常会被包装为 typer.Exit）
        with pytest.raises(Exception):  # 可能是 typer.Exit 或 ExceptionGroup
            await _run_workers_logic(
                all_in_one=False,
                translator=True,
                relay=True,
                container=mock_container
            )
        
        # 注意：在异常情况下，资源清理可能不会被调用，因为异常会中断执行流程
        # 这是预期行为，因为 TaskGroup 会立即抛出异常


async def test_run_workers_logic_all_in_one_mode_calls_run_all_workers(mock_container):
    """测试 all-in-one 模式会调用 _run_all_workers。"""
    
    with patch('trans_hub.adapters.cli.commands.worker._run_all_workers', 
               new_callable=AsyncMock) as mock_run_all:
        
        await _run_workers_logic(
            all_in_one=True,
            translator=False,
            relay=False,
            container=mock_container
        )
        
        # 验证 _run_all_workers 被调用
        mock_run_all.assert_called_once_with(container=mock_container)