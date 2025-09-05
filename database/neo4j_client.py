"""
Neo4j Client module for the Neo4j Organization Information System.
Handles database connections, query execution, and schema management.
"""

import logging
from langchain_community.graphs import Neo4jGraph
from config import Config


class Neo4jClient:
    """
    Handles all Neo4j database operations including:
    - Connection management
    - Query execution with error handling
    - Schema retrieval
    - Spatial index setup
    - APOC verification
    """
    
    def __init__(self):
        """Initialize Neo4j client with connection."""
        try:
            self.graph = Neo4jGraph(
                url=Config.NEO4J_URI,
                username=Config.NEO4J_USERNAME,
                password=Config.NEO4J_PASSWORD
            )
            logging.info("Neo4j connection established successfully")
            
            # Setup spatial indexes and verify APOC
            self._setup_spatial_indexes()
            self._verify_apoc()
            
        except Exception as e:
            logging.error(f"Failed to initialize Neo4j connection: {str(e)}")
            raise
    
    def _setup_spatial_indexes(self):
        """Create spatial indexes if they don't exist."""
        try:
            # Check if spatial index exists
            result = self.query("SHOW INDEXES YIELD name, type WHERE name CONTAINS 'location'")
            
            if not result:
                # Create spatial index
                self.query("CREATE INDEX location_spatial IF NOT EXISTS FOR (l:Location) ON (l.latitude, l.longitude)")
                logging.info("Created spatial index on Location nodes")
            else:
                logging.info("Spatial index already exists")
                
        except Exception as e:
            logging.warning(f"Could not create spatial index: {str(e)}")
    
    def _verify_apoc(self):
        """Verify APOC is available and log status."""
        try:
            result = self.query(
                "CALL apoc.help('toZonedTemporal') YIELD name "
                "RETURN count(name) > 0 AS apoc_available"
            )
            if not result[0]['apoc_available']:
                raise Exception("APOC procedures not installed. Please install APOC plugin.")
            logging.info("APOC temporal functions verified as available")
        except Exception as e:
            logging.error(f"APOC verification failed: {str(e)}")
            raise
    
    def query(self, cypher_query, parameters=None):
        """
        Execute a Cypher query against the Neo4j database.
        
        Args:
            cypher_query (str): Cypher query to execute
            parameters (dict): Optional parameters for the query
            
        Returns:
            list: Query results
            
        Raises:
            Exception: If query execution fails
        """
        try:
            if parameters:
                result = self.graph.query(cypher_query, parameters)
            else:
                result = self.graph.query(cypher_query)
            
            logging.info(f"Query executed successfully, returned {len(result) if result else 0} results")
            return result
            
        except Exception as e:
            logging.error(f"Query execution failed: {str(e)}")
            logging.error(f"Failed query: {cypher_query}")
            raise
    
    def get_schema(self):
        """
        Get the database schema.
        
        Returns:
            str: Database schema information
        """
        try:
            return self.graph.get_schema
        except Exception as e:
            logging.error(f"Failed to retrieve schema: {str(e)}")
            raise
    
    def test_connection(self):
        """
        Test the database connection.
        
        Returns:
            bool: True if connection is working, False otherwise
        """
        try:
            result = self.query("RETURN 1 as test")
            return len(result) > 0 and result[0].get('test') == 1
        except Exception as e:
            logging.error(f"Connection test failed: {str(e)}")
            return False
    
    def get_node_count(self, label=None):
        """
        Get count of nodes, optionally filtered by label.
        
        Args:
            label (str): Optional node label to filter by
            
        Returns:
            int: Number of nodes
        """
        try:
            if label:
                query = f"MATCH (n:{label}) RETURN count(n) as count"
            else:
                query = "MATCH (n) RETURN count(n) as count"
            
            result = self.query(query)
            return result[0]['count'] if result else 0
            
        except Exception as e:
            logging.error(f"Failed to get node count: {str(e)}")
            return 0
    
    def get_relationship_count(self, rel_type=None):
        """
        Get count of relationships, optionally filtered by type.
        
        Args:
            rel_type (str): Optional relationship type to filter by
            
        Returns:
            int: Number of relationships
        """
        try:
            if rel_type:
                query = f"MATCH ()-[r:{rel_type}]-() RETURN count(r) as count"
            else:
                query = "MATCH ()-[r]-() RETURN count(r) as count"
            
            result = self.query(query)
            return result[0]['count'] if result else 0
            
        except Exception as e:
            logging.error(f"Failed to get relationship count: {str(e)}")
            return 0
    
    def close(self):
        """Close the database connection."""
        try:
            if hasattr(self.graph, '_driver') and self.graph._driver:
                self.graph._driver.close()
                logging.info("Neo4j connection closed")
        except Exception as e:
            logging.error(f"Error closing Neo4j connection: {str(e)}")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()