"""
Database migration system for handling schema changes
"""
import logging
from sqlalchemy import text, inspect, Table, MetaData
from sqlalchemy.exc import ProgrammingError

logger = logging.getLogger(__name__)


def check_and_add_missing_columns(engine):
    """
    Check database schema against SQLAlchemy models and add missing columns.
    This handles incremental schema updates without dropping tables.
    
    Args:
        engine: SQLAlchemy engine
    """
    from src.models import Base
    
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    if not existing_tables:
        logger.info("No existing tables found - skipping migration check")
        return
    
    logger.info("Checking for missing columns in existing tables...")
    
    # Check each table in models
    for table in Base.metadata.tables.values():
        table_name = table.name
        
        if table_name not in existing_tables:
            logger.debug(f"Table {table_name} doesn't exist yet - will be created normally")
            continue
        
        # Get existing columns in database
        existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
        
        # Get expected columns from model
        expected_columns = {col.name for col in table.columns}
        
        # Find missing columns
        missing_columns = expected_columns - existing_columns
        
        if missing_columns:
            logger.info(f"Found {len(missing_columns)} missing columns in {table_name}: {missing_columns}")
            _add_missing_columns(engine, table_name, table, missing_columns)
    
    logger.info("Schema check completed")


def _add_missing_columns(engine, table_name: str, table: Table, missing_columns: set):
    """
    Add missing columns to an existing table.
    
    Args:
        engine: SQLAlchemy engine
        table_name: Name of the table
        table: SQLAlchemy Table object
        missing_columns: Set of column names to add
    """
    with engine.begin() as conn:
        for col_name in missing_columns:
            try:
                col = table.columns[col_name]
                
                # Build ALTER TABLE statement
                col_def = _get_column_definition(col)
                
                sql = f'ALTER TABLE "{table_name}" ADD COLUMN {col_def}'
                logger.info(f"Executing migration: {sql}")
                conn.execute(text(sql))
                logger.info(f"✓ Added column {table_name}.{col_name}")
                
            except Exception as e:
                logger.error(f"Error adding column {table_name}.{col_name}: {e}")
                raise


def _get_column_definition(col) -> str:
    """
    Generate SQL column definition from SQLAlchemy Column object.
    
    Args:
        col: SQLAlchemy Column object
        
    Returns:
        SQL column definition string
    """
    col_type = str(col.type.compile())
    col_def = f'"{col.name}" {col_type}'
    
    # Add NOT NULL constraint if applicable
    if col.nullable is False:
        # For existing data, we need a default value for NOT NULL columns
        if col.default is not None:
            col_def += ' DEFAULT NULL'  # Will be set per column if needed
        else:
            col_def += ' NOT NULL DEFAULT NULL'
    
    return col_def


def verify_schema(engine) -> bool:
    """
    Verify that database schema matches SQLAlchemy models.
    
    Args:
        engine: SQLAlchemy engine
        
    Returns:
        True if schema is valid, False otherwise
    """
    from src.models import Base
    
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    schema_valid = True
    
    for table in Base.metadata.tables.values():
        table_name = table.name
        
        if table_name not in existing_tables:
            logger.warning(f"Table {table_name} does not exist in database")
            schema_valid = False
            continue
        
        existing_columns = {col['name'] for col in inspector.get_columns(table_name)}
        expected_columns = {col.name for col in table.columns}
        
        missing_columns = expected_columns - existing_columns
        extra_columns = existing_columns - expected_columns
        
        if missing_columns:
            logger.warning(f"Table {table_name} missing columns: {missing_columns}")
            schema_valid = False
        
        if extra_columns:
            logger.debug(f"Table {table_name} has extra columns: {extra_columns}")
    
    return schema_valid
