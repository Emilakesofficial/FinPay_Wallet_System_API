"""
Performance benchmarking script for wallet system.
Run with: python scripts/benchmark.py
"""
import os
import sys
import django
import time
from decimal import Decimal

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from apps.wallets.models import Wallet
from apps.wallets.services import WalletService

User = get_user_model()


def benchmark_deposits(num_operations=1000):
    """Benchmark deposit operations."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {num_operations} Deposits")
    print(f"{'='*60}")
    
    # Setup
    user, _ = User.objects.get_or_create(
        email='bench@example.com',
        defaults={'username': 'bench', 'password': 'bench123'}
    )
    wallet, _ = Wallet.objects.get_or_create(
        user=user,
        currency='NGN',
        defaults={'name': 'Benchmark Wallet'}
    )
    
    # Benchmark
    start = time.time()
    
    for i in range(num_operations):
        WalletService.deposit(
            wallet_id=str(wallet.id),
            amount=Decimal('10.00'),
            idempotency_key=f'bench-deposit-{int(time.time()*1000000)}-{i}',
            initiated_by=user
        )
    
    duration = time.time() - start
    tps = num_operations / duration
    avg_latency = (duration / num_operations) * 1000
    
    print(f"Duration:     {duration:.2f}s")
    print(f"Throughput:   {tps:.2f} TPS")
    print(f"Avg Latency:  {avg_latency:.2f}ms")
    print(f"Final Balance: #{wallet.get_balance()}")


def benchmark_balance_queries(num_operations=10000):
    """Benchmark balance query operations."""
    print(f"\n{'='*60}")
    print(f"BENCHMARK: {num_operations} Balance Queries")
    print(f"{'='*60}")
    
    user, _ = User.objects.get_or_create(
        email='bench@example.com',
        defaults={'username': 'bench', 'password': 'bench123'}
    )
    wallet, _ = Wallet.objects.get_or_create(
        user=user,
        currency='NGN',
        defaults={'name': 'Benchmark Wallet'}
    )
    
    start = time.time()
    
    for i in range(num_operations):
        balance = wallet.get_balance()
    
    duration = time.time() - start
    qps = num_operations / duration
    avg_latency = (duration / num_operations) * 1000
    
    print(f"Duration:     {duration:.2f}s")
    print(f"Throughput:   {qps:.2f} QPS")
    print(f"Avg Latency:  {avg_latency:.4f}ms")


if __name__ == '__main__':
    print("\n🚀 Wallet System Performance Benchmark")
    
    benchmark_deposits(1000)
    benchmark_balance_queries(10000)
    
    print(f"\n{'='*60}")
    print("✅ Benchmark Complete")
    print(f"{'='*60}\n")