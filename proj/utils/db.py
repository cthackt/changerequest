import pandas as pd
import re

# This function allows you to put in a table name and get back the primary key fields of the table
def get_primary_key(tablename, eng):
    
    # This query gets us the primary keys of a table. Not in a python friendly format
    # Copy paste to Navicat, pgadmin, or do a pd.read_sql to see what it gives
    pkey_query = f"""
        SELECT 
            conrelid::regclass AS table_from, 
            conname, 
            pg_get_constraintdef(oid) 
        FROM pg_constraint 
        WHERE 
            contype IN ('f', 'p') 
            AND connamespace = 'sde'::regnamespace 
            AND conname LIKE '{tablename}%%' 
        ORDER BY 
            conrelid::regclass::text, contype DESC;
    """
    pkey_df = pd.read_sql(pkey_query, eng)
    
    pkey = []
    # sometimes there is no primary key
    if not pkey_df.empty:
        # pg_get_constraintdef = postgres get constraint definition
        # Get the primary key constraint's definition
        pkey = pkey_df.pg_get_constraintdef.tolist()[0]

        # Remove excess junk to just get the primary key field names
        # split at the commas to get a nice neat python list
        pkey = re.sub(r"(PRIMARY\sKEY\s\()|(\))","",pkey).split(',')

        # remove whitespace from the edges
        pkey = [colname.strip() for colname in pkey]
        
    return pkey

    
# for the checkDataTypes function in core_checks
def dtype_translator(dtype: str, human_readable = False):
    if dtype is None:
        return None
    if bool(re.search('INT', dtype.upper())):
        return int if not human_readable else "Integer"
    elif dtype.upper() in ('VARCHAR', 'TEXT'):
        return str if not human_readable else "Text"
    elif dtype.upper() in ('NUMERIC','DOUBLE_PRECISION','FLOAT', 'DOUBLE PRECISION'):
        return float if not human_readable else "Numeric"
    elif bool(re.search('TIMESTAMP', dtype.upper())):
        return pd.Timestamp if not human_readable else "Date"
    else:
        return dtype
    

# Gets the information about precision and length for database table columns
def get_precision(coltype):
    
    # numeric and decimal types get read in like this
    # NUMERIC(5, 2) where 5 is the precision and 2 is the scale
    # Same for the DECIMALs if i am not mistaken
    if bool(re.search('(NUMERIC|DECIMAL)', str(coltype))):
        return {
            'coltype': re.search('(NUMERIC|DECIMAL)', str(coltype)).groups()[0],
            'precision': int(
                re.search(
                    '(\w*)\((.*)\)', str(coltype)
                ) \
                .groups()[-1] \
                .split(',')[0] \
                .strip()
            )
            , 
            'scale': int(
                re.search(
                    '(\w*)\((.*)\)', str(coltype)
                ) \
                .groups()[-1] \
                .split(',')[-1] \
                .strip()
            )
        }
        
    # VARCHARS are read in like this
    # VARCHAR(255) where 255 is the max length of the string
    elif bool(re.search('VARCHAR', str(coltype))):
        return {
            'coltype': 'VARCHAR',
            'length': int(re.search('(\w*)\((\d*)\)', str(coltype)).groups()[-1])
        } 
    
    # Max sizes of the various integer types according to the PostgreSQL documentation
    elif bool(re.search('SMALLINT', str(coltype))):
        return {'coltype': 'SMALLINT', 'min': -32767, 'max': 32767}
    
    elif bool(re.search('INTEGER', str(coltype))):
        return {'coltype': 'INTEGER', 'min': -2147483648, 'max': 2147483648}
    
    elif bool(re.search('BIGINT', str(coltype))):
        return {'coltype': 'BIGINT', 'min': -9223372036854775807, 'max': 9223372036854775807}
    
    elif bool(re.search('SERIAL', str(coltype))):
        return {'coltype': 'SERIAL', 'min': 1, 'max': 2147483647}
    
    elif bool(re.search('BIGSERIAL', str(coltype))):
        return {'coltype': 'BIGSERIAL', 'min':1, 'max': 9223372036854775807}
    
    else:
        return {'coltype': str(coltype)}
    
    
# Gets the info on a table's column from the database
def fetch_metadata(tablename, eng, system_fields = []):

    # We need to adjust this query to fetch the metadata from the information schema
    # This "cols =" code is more recent, however the remaining code is dependent on our previous method of gettign metadata
    #  which was to use the sqlalchemy class MetaData(eng)
    # It was a lot faster to get the necessary information directly from the database with a query,
    # That query should be in the repository that has the new version of the checker
    cols = pd.read_sql(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{tablename}'", eng).column_name.tolist()

    return [
        {
            "column_name": col, 
            "original_dtype": str(col.type),
            "column_dtype": dtype_translator(
                re.search(
                    '(\w*)\((\w*\=)*(\d*)', str(col.type)
                ).groups()[0] 
                if bool(re.search('(\w*)\((\w*\=)*(\d*)', str(col.type))) 
                else str(col.type)
            ) if col not in ('result','mdl') else float,
            "human_readable_column_dtype": dtype_translator(
                re.search(
                    '(\w*)\((\w*\=)*(\d*)', str(col.type)
                ).groups()[0] 
                if bool(re.search('(\w*)\((\w*\=)*(\d*)', str(col.type))) 
                else str(col.type)
                , 
                human_readable = True
            ) if col not in ('result','mdl') else "Numeric",
            "column_precision": get_precision(str(col.type))
        } 
        for col in [c for c in cols if c not in system_fields ]
    ]