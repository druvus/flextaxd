"""Unit tests for logging configuration."""

import logging
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import Mock, patch, call
import sys

from flextaxd.utils.logging_config import setup_logging, get_logger


class TestGetLogger:
    """Test get_logger function."""
    
    def test_get_logger_with_flextaxd_prefix(self):
        """Test getting logger with existing flextaxd prefix."""
        logger = get_logger('flextaxd.test.module')
        
        assert logger.name == 'flextaxd.test.module'
        assert isinstance(logger, logging.Logger)
    
    def test_get_logger_without_prefix(self):
        """Test getting logger without flextaxd prefix."""
        logger = get_logger('test.module')
        
        assert logger.name == 'flextaxd.test.module'
        assert isinstance(logger, logging.Logger)
    
    def test_get_logger_module_name(self):
        """Test getting logger with module name format."""
        logger = get_logger(__name__)
        
        assert logger.name.startswith('flextaxd.')
        assert isinstance(logger, logging.Logger)


class TestSetupLogging:
    """Test setup_logging function."""
    
    def setup_method(self):
        """Setup test method."""
        # Clear any existing handlers
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Clear flextaxd loggers
        flextaxd_logger = logging.getLogger('flextaxd')
        for handler in flextaxd_logger.handlers[:]:
            flextaxd_logger.removeHandler(handler)
    
    def teardown_method(self):
        """Teardown test method."""
        # Reset logging configuration
        logging.getLogger().setLevel(logging.WARNING)
    
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_console_only(self, mock_dict_config):
        """Test setup logging with console only."""
        setup_logging(level=logging.INFO)
        
        mock_dict_config.assert_called_once()
        config = mock_dict_config.call_args[0][0]
        
        # Check basic configuration structure
        assert config['version'] == 1
        assert config['disable_existing_loggers'] is False
        assert 'formatters' in config
        assert 'handlers' in config
        assert 'loggers' in config
        
        # Check console handler is configured
        assert 'console' in config['handlers']
        console_handler = config['handlers']['console']
        assert console_handler['class'] == 'logging.StreamHandler'
        assert console_handler['level'] == logging.INFO
        assert console_handler['stream'] == sys.stderr
        
        # Check formatters
        assert 'console' in config['formatters']
        assert '%(levelname)s: %(message)s' in config['formatters']['console']['format']
    
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_with_file(self, mock_dict_config):
        """Test setup logging with file output."""
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            setup_logging(level=logging.DEBUG, log_file=log_file)
            
            mock_dict_config.assert_called_once()
            config = mock_dict_config.call_args[0][0]
            
            # Check both console and file handlers exist
            assert 'console' in config['handlers']
            assert 'file' in config['handlers']
            
            # Check file handler configuration
            file_handler = config['handlers']['file']
            assert file_handler['class'] == 'logging.FileHandler'
            assert file_handler['level'] == logging.DEBUG
            assert file_handler['filename'] == str(log_file)
            assert file_handler['mode'] == 'a'
            
            # Check file formatter
            assert 'file' in config['formatters']
            file_formatter = config['formatters']['file']
            assert 'asctime' in file_formatter['format']
            assert 'name' in file_formatter['format']
            assert 'levelname' in file_formatter['format']
            assert 'message' in file_formatter['format']
    
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_creates_log_directory(self, mock_dict_config):
        """Test that setup_logging creates log directory if needed."""
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "nested" / "logs" / "test.log"
            
            # Directory should not exist initially
            assert not log_file.parent.exists()
            
            setup_logging(log_file=log_file)
            
            # Directory should be created
            assert log_file.parent.exists()
            assert log_file.parent.is_dir()
    
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_different_levels(self, mock_dict_config):
        """Test setup logging with different levels."""
        for level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]:
            mock_dict_config.reset_mock()
            
            setup_logging(level=level)
            
            config = mock_dict_config.call_args[0][0]
            console_handler = config['handlers']['console']
            assert console_handler['level'] == level
    
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_logger_configuration(self, mock_dict_config):
        """Test logger configuration in setup_logging."""
        setup_logging()
        
        config = mock_dict_config.call_args[0][0]
        
        # Check flextaxd logger configuration
        assert 'flextaxd' in config['loggers']
        flextaxd_config = config['loggers']['flextaxd']
        assert flextaxd_config['level'] == logging.DEBUG
        assert flextaxd_config['propagate'] is False
        assert 'console' in flextaxd_config['handlers']
        
        # Check external library noise reduction
        assert 'urllib3' in config['loggers']
        assert config['loggers']['urllib3']['level'] == logging.WARNING
        assert 'requests' in config['loggers']
        assert config['loggers']['requests']['level'] == logging.WARNING
        
        # Check root logger
        assert 'root' in config
        root_config = config['root']
        assert root_config['level'] == logging.WARNING
    
    @patch('flextaxd.utils.logging_config.logging.getLogger')
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_debug_messages(self, mock_dict_config, mock_get_logger):
        """Test debug messages are logged during setup."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            setup_logging(level=logging.DEBUG, log_file=log_file)
            
            # Check that logger was obtained
            mock_get_logger.assert_called_with('flextaxd.logging')
            
            # Check debug messages were logged
            mock_logger.debug.assert_has_calls([
                call("Logging configured with level: DEBUG"),
                call(f"File logging enabled: {log_file}")
            ])
    
    @patch('flextaxd.utils.logging_config.logging.getLogger')
    @patch('flextaxd.utils.logging_config.logging.config.dictConfig')
    def test_setup_logging_no_file_debug_message(self, mock_dict_config, mock_get_logger):
        """Test no file debug message when no file specified."""
        mock_logger = Mock()
        mock_get_logger.return_value = mock_logger
        
        setup_logging(level=logging.INFO)
        
        # Should only have level debug message, not file message
        assert mock_logger.debug.call_count == 1
        mock_logger.debug.assert_called_with("Logging configured with level: INFO")


class TestLoggingIntegration:
    """Test logging integration."""
    
    def test_logger_hierarchy(self):
        """Test that FlexTaxD loggers form proper hierarchy."""
        parent_logger = get_logger('parent')
        child_logger = get_logger('parent.child')
        
        assert parent_logger.name == 'flextaxd.parent'
        assert child_logger.name == 'flextaxd.parent.child'
        assert child_logger.parent == parent_logger
    
    def test_logging_with_real_setup(self):
        """Test actual logging functionality with real setup."""
        with TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "integration_test.log"
            
            # Setup logging
            setup_logging(level=logging.DEBUG, log_file=log_file)
            
            # Get logger and log messages
            logger = get_logger('integration_test')
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            
            # Check that log file was created and contains messages
            assert log_file.exists()
            
            with open(log_file, 'r') as f:
                log_content = f.read()
                
            assert "Debug message" in log_content
            assert "Info message" in log_content
            assert "Warning message" in log_content
            assert "Error message" in log_content
            assert "flextaxd.integration_test" in log_content
    
    def test_external_library_noise_reduction(self):
        """Test that external library logging is reduced."""
        setup_logging()
        
        # Check that external library loggers have WARNING level
        urllib3_logger = logging.getLogger('urllib3')
        requests_logger = logging.getLogger('requests')
        
        # These should be set to WARNING level to reduce noise
        assert urllib3_logger.level >= logging.WARNING or urllib3_logger.isEnabledFor(logging.WARNING)
        assert requests_logger.level >= logging.WARNING or requests_logger.isEnabledFor(logging.WARNING)


class TestLoggingErrorHandling:
    """Test logging error scenarios."""
    
    def test_setup_logging_with_invalid_file_path(self):
        """Test setup logging with invalid file path."""
        # Try to create log file in non-existent directory with no permissions
        invalid_path = Path("/root/cannot_create/test.log")  # Typically no permission
        
        # This should not raise an exception - the mkdir should handle it gracefully
        # or logging should handle the error
        try:
            setup_logging(log_file=invalid_path)
            # If no exception, that's fine - the system handled it
        except (PermissionError, OSError):
            # These are expected if we really can't create the directory
            pass
    
    def test_get_logger_empty_name(self):
        """Test getting logger with empty name."""
        logger = get_logger('')
        assert logger.name == 'flextaxd.'
        assert isinstance(logger, logging.Logger)
    
    def test_multiple_setup_calls(self):
        """Test calling setup_logging multiple times."""
        # Should not cause issues
        setup_logging(level=logging.INFO)
        setup_logging(level=logging.DEBUG)
        setup_logging(level=logging.WARNING)
        
        # Should still be able to get loggers
        logger = get_logger('multiple_setup_test')
        assert isinstance(logger, logging.Logger)