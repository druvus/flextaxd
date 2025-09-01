"""Adaptive caching strategies for high-performance taxonomy operations."""

from __future__ import annotations
import threading
import time
import heapq
from typing import Dict, Any, Optional, Tuple, Set, List, TypeVar, Generic
from dataclasses import dataclass, field
from collections import defaultdict, OrderedDict
import weakref
import gc

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """Advanced cache entry with access patterns and frequency tracking."""
    
    value: T
    last_access: float = field(default_factory=time.time)
    access_count: int = 0
    creation_time: float = field(default_factory=time.time)
    access_frequency: float = 0.0  # Accesses per second
    size_estimate: int = 0
    priority_score: float = 0.0
    
    def update_access(self):
        """Update access statistics."""
        current_time = time.time()
        self.access_count += 1
        
        # Calculate frequency (exponential moving average)
        time_diff = current_time - self.last_access
        if time_diff > 0:
            instant_frequency = 1.0 / time_diff
            alpha = 0.1  # Smoothing factor
            self.access_frequency = alpha * instant_frequency + (1 - alpha) * self.access_frequency
        
        self.last_access = current_time
        
        # Update priority score (combines frequency, recency, and age)
        age_factor = 1.0 / (1.0 + (current_time - self.creation_time) / 3600)  # Decay over hours
        recency_factor = 1.0 / (1.0 + (current_time - self.last_access) / 60)  # Decay over minutes
        
        self.priority_score = (
            self.access_frequency * 0.4 +
            self.access_count * 0.3 +
            recency_factor * 0.2 +
            age_factor * 0.1
        )


class AdaptiveLRUCache(Generic[T]):
    """Advanced LRU cache with adaptive sizing and hot/cold regions."""
    
    def __init__(self, max_size: int = 1000, hot_ratio: float = 0.3):
        """Initialize adaptive cache."""
        self.max_size = max_size
        self.hot_size = int(max_size * hot_ratio)
        self.cold_size = max_size - self.hot_size
        
        # Hot region: frequently accessed items
        self._hot_cache: OrderedDict[Any, CacheEntry[T]] = OrderedDict()
        
        # Cold region: less frequently accessed items  
        self._cold_cache: OrderedDict[Any, CacheEntry[T]] = OrderedDict()
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._promotions = 0
        self._demotions = 0
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Adaptive sizing
        self._hit_rates = []
        self._last_resize = time.time()
        self._resize_interval = 60.0  # Resize every minute
    
    def get(self, key: Any) -> Optional[T]:
        """Get item from cache with adaptive management."""
        with self._lock:
            # Check hot cache first
            if key in self._hot_cache:
                entry = self._hot_cache[key]
                entry.update_access()
                # Move to end (most recently used)
                self._hot_cache.move_to_end(key)
                self._hits += 1
                return entry.value
            
            # Check cold cache
            if key in self._cold_cache:
                entry = self._cold_cache[key]
                entry.update_access()
                
                # Promote to hot cache if access frequency is high
                if self._should_promote(entry):
                    self._promote_to_hot(key, entry)
                    self._promotions += 1
                else:
                    # Move to end in cold cache
                    self._cold_cache.move_to_end(key)
                
                self._hits += 1
                return entry.value
            
            # Cache miss
            self._misses += 1
            return None
    
    def put(self, key: Any, value: T, size_hint: int = 1) -> None:
        """Put item in cache with adaptive placement."""
        with self._lock:
            entry = CacheEntry(
                value=value,
                size_estimate=size_hint
            )
            entry.update_access()
            
            # Remove from existing location if present
            if key in self._hot_cache:
                del self._hot_cache[key]
            elif key in self._cold_cache:
                del self._cold_cache[key]
            
            # Place in hot cache (new items are considered hot)
            self._hot_cache[key] = entry
            
            # Maintain size limits
            self._maintain_size_limits()
            
            # Adaptive resizing
            self._maybe_resize_cache()
    
    def _should_promote(self, entry: CacheEntry[T]) -> bool:
        """Determine if entry should be promoted to hot cache."""
        # Promote if high access frequency or very recent access
        return (
            entry.access_frequency > 0.1 or  # More than 1 access per 10 seconds
            entry.access_count > 5 or        # Accessed many times
            time.time() - entry.last_access < 5  # Very recent access
        )
    
    def _promote_to_hot(self, key: Any, entry: CacheEntry[T]):
        """Promote entry from cold to hot cache."""
        # Remove from cold
        if key in self._cold_cache:
            del self._cold_cache[key]
        
        # Add to hot
        self._hot_cache[key] = entry
        self._hot_cache.move_to_end(key)
    
    def _demote_to_cold(self, key: Any, entry: CacheEntry[T]):
        """Demote entry from hot to cold cache."""
        # Remove from hot
        if key in self._hot_cache:
            del self._hot_cache[key]
        
        # Add to cold
        self._cold_cache[key] = entry
        self._cold_cache.move_to_end(key)
        self._demotions += 1
    
    def _maintain_size_limits(self):
        """Maintain cache size limits and manage hot/cold regions."""
        # Evict from hot cache if over limit
        while len(self._hot_cache) > self.hot_size:
            # Find least priority item in hot cache
            min_key = min(
                self._hot_cache.keys(),
                key=lambda k: self._hot_cache[k].priority_score
            )
            entry = self._hot_cache[min_key]
            
            # Demote to cold if still valuable, otherwise evict
            if entry.access_count > 1 and len(self._cold_cache) < self.cold_size:
                self._demote_to_cold(min_key, entry)
            else:
                del self._hot_cache[min_key]
                self._evictions += 1
        
        # Evict from cold cache if over limit
        while len(self._cold_cache) > self.cold_size:
            # Remove least recently used from cold
            key, _ = self._cold_cache.popitem(last=False)
            self._evictions += 1
    
    def _maybe_resize_cache(self):
        """Adaptively resize cache based on hit rate trends."""
        current_time = time.time()
        
        if current_time - self._last_resize < self._resize_interval:
            return
        
        # Calculate current hit rate
        total_accesses = self._hits + self._misses
        if total_accesses < 100:  # Not enough data
            return
        
        current_hit_rate = self._hits / total_accesses
        self._hit_rates.append(current_hit_rate)
        
        # Keep only recent history
        if len(self._hit_rates) > 10:
            self._hit_rates = self._hit_rates[-10:]
        
        # Resize if hit rate is consistently low or high
        if len(self._hit_rates) >= 3:
            avg_hit_rate = sum(self._hit_rates) / len(self._hit_rates)
            
            if avg_hit_rate < 0.7 and self.max_size < 10000:
                # Increase cache size
                old_size = self.max_size
                self.max_size = min(self.max_size * 2, 10000)
                self.hot_size = int(self.max_size * 0.3)
                self.cold_size = self.max_size - self.hot_size
                print(f"Cache resized: {old_size} -> {self.max_size} (hit rate: {avg_hit_rate:.1%})")
            
            elif avg_hit_rate > 0.95 and self.max_size > 100:
                # Decrease cache size
                old_size = self.max_size
                self.max_size = max(self.max_size // 2, 100)
                self.hot_size = int(self.max_size * 0.3)
                self.cold_size = self.max_size - self.hot_size
                print(f"Cache resized: {old_size} -> {self.max_size} (hit rate: {avg_hit_rate:.1%})")
                
                # Evict excess entries
                self._maintain_size_limits()
        
        self._last_resize = current_time
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        total_accesses = self._hits + self._misses
        hit_rate = self._hits / total_accesses if total_accesses > 0 else 0
        
        with self._lock:
            return {
                'max_size': self.max_size,
                'hot_size_limit': self.hot_size,
                'cold_size_limit': self.cold_size,
                'hot_cache_size': len(self._hot_cache),
                'cold_cache_size': len(self._cold_cache),
                'total_size': len(self._hot_cache) + len(self._cold_cache),
                'hit_rate': hit_rate * 100,
                'hits': self._hits,
                'misses': self._misses,
                'evictions': self._evictions,
                'promotions': self._promotions,
                'demotions': self._demotions,
                'hot_cache_usage': len(self._hot_cache) / self.hot_size * 100,
                'cold_cache_usage': len(self._cold_cache) / self.cold_size * 100
            }
    
    def clear(self):
        """Clear cache and reset statistics."""
        with self._lock:
            self._hot_cache.clear()
            self._cold_cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0
            self._promotions = 0
            self._demotions = 0
            self._hit_rates.clear()


class PredictiveCache:
    """Predictive cache that preloads likely-to-be-accessed items."""
    
    def __init__(self, base_cache: AdaptiveLRUCache, prefetch_size: int = 100):
        self.base_cache = base_cache
        self.prefetch_size = prefetch_size
        
        # Access pattern tracking
        self._access_history: List[Any] = []
        self._access_patterns: Dict[Any, List[Any]] = defaultdict(list)
        self._prediction_success = 0
        self._prediction_attempts = 0
        
        # Background prefetching
        self._prefetch_queue: Set[Any] = set()
        self._prefetch_lock = threading.Lock()
    
    def get(self, key: Any, loader_func=None) -> Optional[T]:
        """Get with predictive prefetching."""
        # Track access pattern
        self._record_access(key)
        
        # Get from base cache
        result = self.base_cache.get(key)
        
        if result is None and loader_func:
            # Load and cache
            result = loader_func(key)
            if result is not None:
                self.base_cache.put(key, result)
        
        # Trigger predictive prefetching
        self._maybe_prefetch(key, loader_func)
        
        return result
    
    def _record_access(self, key: Any):
        """Record access for pattern analysis."""
        self._access_history.append(key)
        
        # Keep limited history
        if len(self._access_history) > 1000:
            self._access_history = self._access_history[-500:]
        
        # Update patterns (look at last few accesses)
        if len(self._access_history) >= 2:
            prev_key = self._access_history[-2]
            self._access_patterns[prev_key].append(key)
            
            # Keep pattern history limited
            if len(self._access_patterns[prev_key]) > 10:
                self._access_patterns[prev_key] = self._access_patterns[prev_key][-5:]
    
    def _maybe_prefetch(self, key: Any, loader_func):
        """Predictively prefetch likely next accesses."""
        if not loader_func:
            return
        
        # Get predicted next accesses
        predictions = self._predict_next_accesses(key)
        
        with self._prefetch_lock:
            for predicted_key in predictions[:self.prefetch_size]:
                if predicted_key not in self._prefetch_queue:
                    if self.base_cache.get(predicted_key) is None:
                        # Start background prefetch
                        self._prefetch_queue.add(predicted_key)
                        
                        def prefetch():
                            try:
                                value = loader_func(predicted_key)
                                if value is not None:
                                    self.base_cache.put(predicted_key, value)
                                    self._prediction_success += 1
                            except Exception:
                                pass
                            finally:
                                with self._prefetch_lock:
                                    self._prefetch_queue.discard(predicted_key)
                        
                        # Submit prefetch task
                        threading.Thread(target=prefetch, daemon=True).start()
                        self._prediction_attempts += 1
    
    def _predict_next_accesses(self, key: Any) -> List[Any]:
        """Predict likely next accesses based on patterns."""
        predictions = []
        
        # Get direct patterns for this key
        if key in self._access_patterns:
            # Sort by frequency
            pattern_freq = defaultdict(int)
            for next_key in self._access_patterns[key]:
                pattern_freq[next_key] += 1
            
            # Add most frequent patterns
            sorted_patterns = sorted(pattern_freq.items(), key=lambda x: x[1], reverse=True)
            predictions.extend([k for k, _ in sorted_patterns[:5]])
        
        # Add sequential patterns (common in tree traversal)
        if isinstance(key, int):
            # Predict sequential access
            predictions.extend([key + i for i in range(1, 6)])
            predictions.extend([key - i for i in range(1, 6)])
        
        return predictions[:self.prefetch_size]
    
    def get_prediction_accuracy(self) -> float:
        """Get prefetch prediction accuracy."""
        if self._prediction_attempts == 0:
            return 0.0
        return self._prediction_success / self._prediction_attempts * 100


class HierarchicalCache:
    """Multi-level cache optimized for tree hierarchies."""
    
    def __init__(self, l1_size: int = 100, l2_size: int = 1000, l3_size: int = 10000):
        """Initialize hierarchical cache."""
        
        # L1: Tiny, ultra-fast cache for most recent items
        self.l1_cache: OrderedDict[Any, T] = OrderedDict()
        self.l1_size = l1_size
        
        # L2: Medium cache with frequency tracking
        self.l2_cache = AdaptiveLRUCache[T](l2_size)
        
        # L3: Large cache for bulk storage
        self.l3_cache: OrderedDict[Any, T] = OrderedDict() 
        self.l3_size = l3_size
        
        # Statistics
        self._l1_hits = 0
        self._l2_hits = 0  
        self._l3_hits = 0
        self._misses = 0
        
        self._lock = threading.RLock()
    
    def get(self, key: Any) -> Optional[T]:
        """Get from hierarchical cache."""
        with self._lock:
            # L1 check (fastest)
            if key in self.l1_cache:
                self.l1_cache.move_to_end(key)
                self._l1_hits += 1
                return self.l1_cache[key]
            
            # L2 check
            l2_result = self.l2_cache.get(key)
            if l2_result is not None:
                # Promote to L1
                self._promote_to_l1(key, l2_result)
                self._l2_hits += 1
                return l2_result
            
            # L3 check  
            if key in self.l3_cache:
                value = self.l3_cache[key]
                # Promote to L2
                self.l2_cache.put(key, value)
                del self.l3_cache[key]
                self._l3_hits += 1
                return value
            
            # Cache miss
            self._misses += 1
            return None
    
    def put(self, key: Any, value: T):
        """Put into hierarchical cache."""
        with self._lock:
            # Always start in L1
            self._promote_to_l1(key, value)
    
    def _promote_to_l1(self, key: Any, value: T):
        """Promote item to L1 cache."""
        # Remove from other levels
        if key in self.l3_cache:
            del self.l3_cache[key]
        
        # Add to L1
        self.l1_cache[key] = value
        self.l1_cache.move_to_end(key)
        
        # Maintain L1 size
        while len(self.l1_cache) > self.l1_size:
            # Demote LRU item to L2
            old_key, old_value = self.l1_cache.popitem(last=False)
            self.l2_cache.put(old_key, old_value)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        total_accesses = self._l1_hits + self._l2_hits + self._l3_hits + self._misses
        
        stats = {
            'l1_size': len(self.l1_cache),
            'l1_hits': self._l1_hits,
            'l1_hit_rate': self._l1_hits / total_accesses * 100 if total_accesses > 0 else 0,
            
            'l2_hits': self._l2_hits,
            'l2_hit_rate': self._l2_hits / total_accesses * 100 if total_accesses > 0 else 0,
            
            'l3_size': len(self.l3_cache),
            'l3_hits': self._l3_hits,
            'l3_hit_rate': self._l3_hits / total_accesses * 100 if total_accesses > 0 else 0,
            
            'total_hits': self._l1_hits + self._l2_hits + self._l3_hits,
            'total_misses': self._misses,
            'overall_hit_rate': (self._l1_hits + self._l2_hits + self._l3_hits) / total_accesses * 100 if total_accesses > 0 else 0,
            
            'total_accesses': total_accesses
        }
        
        # Add L2 adaptive cache stats
        l2_stats = self.l2_cache.get_statistics()
        stats['l2_adaptive_stats'] = l2_stats
        
        return stats


class CacheWarmer:
    """Intelligent cache warming strategies for taxonomy trees."""
    
    def __init__(self, tree, cache):
        self.tree = tree
        self.cache = cache
    
    def warm_by_access_patterns(self, access_log: List[int], 
                              preload_factor: float = 2.0):
        """Warm cache based on historical access patterns."""
        # Analyze access patterns
        access_freq = defaultdict(int)
        for node_id in access_log:
            access_freq[node_id] += 1
        
        # Preload most frequently accessed nodes
        frequent_nodes = sorted(access_freq.items(), key=lambda x: x[1], reverse=True)
        preload_count = int(len(frequent_nodes) * preload_factor / 100)
        
        for node_id, freq in frequent_nodes[:preload_count]:
            if hasattr(self.tree, 'get_node'):
                self.tree.get_node(node_id)  # Trigger cache loading
    
    def warm_by_hierarchy_levels(self, max_depth: int = 5):
        """Warm cache by preloading upper hierarchy levels."""
        # Start from root and preload by levels
        if hasattr(self.tree, 'root_id') and self.tree.root_id:
            self._warm_subtree_bfs(self.tree.root_id, max_depth)
    
    def _warm_subtree_bfs(self, root_id: int, max_depth: int):
        """Warm cache using breadth-first traversal."""
        queue = [(root_id, 0)]
        
        while queue:
            node_id, depth = queue.pop(0)
            
            if depth > max_depth:
                continue
            
            # Load node (triggers caching)
            if hasattr(self.tree, 'get_node'):
                self.tree.get_node(node_id)
            
            # Add children to queue
            if hasattr(self.tree, 'get_children'):
                children = self.tree.get_children(node_id)
                for child_id in children:
                    queue.append((child_id, depth + 1))


def create_adaptive_cache(max_size: int = 1000, 
                         hot_ratio: float = 0.3) -> AdaptiveLRUCache:
    """Factory function for adaptive cache."""
    return AdaptiveLRUCache(max_size, hot_ratio)


def create_hierarchical_cache(l1_size: int = 100, 
                             l2_size: int = 1000, 
                             l3_size: int = 10000) -> HierarchicalCache:
    """Factory function for hierarchical cache."""
    return HierarchicalCache(l1_size, l2_size, l3_size)