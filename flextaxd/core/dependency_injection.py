"""Simple dependency injection system for better testability."""

from typing import TypeVar, Type, Dict, Any, Callable, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Generic
from abc import ABC, abstractmethod
from functools import wraps

T = TypeVar('T')


class DIContainer:
    """Simple dependency injection container."""
    
    def __init__(self) -> None:
        self._services: Dict[Type[Any], Any] = {}
        self._factories: Dict[Type[Any], Callable[[], Any]] = {}
        self._singletons: Dict[Type[Any], Any] = {}
    
    def register_instance(self, service_type: Type[T], instance: T) -> None:
        """Register a service instance."""
        self._services[service_type] = instance
    
    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Register a service factory."""
        self._factories[service_type] = factory
    
    def register_singleton(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Register a singleton service."""
        self._factories[service_type] = factory
        self._singletons[service_type] = None
    
    def get(self, service_type: Type[T]) -> T:
        """Get a service instance."""
        # Check for direct instance registration
        if service_type in self._services:
            return self._services[service_type]  # type: ignore[no-any-return]
        
        # Check for singleton
        if service_type in self._singletons:
            if self._singletons[service_type] is None:
                self._singletons[service_type] = self._factories[service_type]()
            return self._singletons[service_type]  # type: ignore[no-any-return]
        
        # Check for factory
        if service_type in self._factories:
            return self._factories[service_type]()  # type: ignore[no-any-return]
        
        # Try to create instance directly
        try:
            return service_type()
        except Exception as e:
            raise ValueError(f"Cannot create instance of {service_type}: {e}")
    
    def clear(self) -> None:
        """Clear all registrations."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()


# Global container instance
_container = DIContainer()


def get_container() -> DIContainer:
    """Get the global DI container."""
    return _container


def inject(service_type: Type[T]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to inject a service into a function parameter.
    
    Usage:
        @inject(DatabaseService)
        def my_function(db: DatabaseService):
            # db will be injected automatically
            pass
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # If the service is not already provided, inject it
            import inspect
            sig = inspect.signature(func)
            param_names = list(sig.parameters.keys())
            
            if len(args) < len(param_names):
                # Get the parameter name for this service type
                param_name = param_names[len(args)]
                if param_name not in kwargs:
                    # Inject the service
                    kwargs[param_name] = get_container().get(service_type)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Service interfaces for testing
class DatabaseService(ABC):
    """Abstract database service interface."""
    
    @abstractmethod
    def save_tree(self, tree: Any) -> None:
        """Save a taxonomy tree."""
        pass
    
    @abstractmethod
    def load_tree(self) -> Any:
        """Load a taxonomy tree."""
        pass


class ParserService(ABC):
    """Abstract parser service interface."""
    
    @abstractmethod
    def parse(self, file_path: Any) -> Any:
        """Parse a taxonomy file."""
        pass


class ExporterService(ABC):
    """Abstract exporter service interface."""
    
    @abstractmethod
    def export(self, tree: Any, output_path: Any) -> None:
        """Export a taxonomy tree."""
        pass


# Configuration for dependency injection
def configure_production_services() -> None:
    """Configure services for production use."""
    from ..database.sqlite import SQLiteTaxonomyRepository
    from ..parsers.registry import ParserRegistry
    # from ..exporters.registry import ExporterRegistry  # TODO: Create this when needed
    
    # Register default implementations
    container = get_container()
    
    # Database service factory
    def db_factory() -> Any:
        import os
        db_path = os.getenv('FLEXTAXD_DB_PATH', 'taxonomy.ftd')
        return SQLiteTaxonomyRepository(db_path)
    
    container.register_factory(DatabaseService, db_factory)  # type: ignore[type-abstract]
    container.register_singleton(ParserService, lambda: ParserRegistry())  # type: ignore[type-abstract,arg-type,return-value]
    # container.register_singleton(ExporterService, lambda: ExporterRegistry())  # TODO: Implement when needed


def configure_test_services() -> None:
    """Configure services for testing."""
    container = get_container()
    container.clear()  # Clear any existing registrations
    
    # Mock implementations would be registered here
    # For now, we'll use the same production services
    configure_production_services()


# Context manager for temporary service overrides
class ServiceOverride:
    """Context manager for temporarily overriding services."""
    
    def __init__(self, service_type: Type[Any], instance: Any) -> None:
        self.service_type = service_type
        self.instance = instance
        self.original_instance: Optional[Any] = None
        self.had_original = False
    
    def __enter__(self) -> Any:
        container = get_container()
        
        # Save original if it exists
        if self.service_type in container._services:
            self.original_instance = container._services[self.service_type]
            self.had_original = True
        
        # Set override
        container.register_instance(self.service_type, self.instance)
        return self.instance
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        container = get_container()
        
        if self.had_original:
            # Restore original
            container.register_instance(self.service_type, self.original_instance)
        else:
            # Remove override
            container._services.pop(self.service_type, None)


def with_service(service_type: Type[Any], instance: Any) -> ServiceOverride:
    """Create a service override context manager.
    
    Usage:
        with with_service(DatabaseService, mock_db):
            # mock_db will be used instead of the normal database service
            pass
    """
    return ServiceOverride(service_type, instance)


# Initialize production services by default (only if needed)
# configure_production_services()  # Commented out to avoid import issues during development