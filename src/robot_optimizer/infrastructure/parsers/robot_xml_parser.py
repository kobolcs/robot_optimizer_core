# src/robot_optimizer/infrastructure/parsers/robot_xml_parser.py
"""Parser for Robot Framework XML output files."""
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import List

from ...domain.value_objects.test_result import TestResult


class RobotXmlParser:
    """Parser for Robot Framework output.xml files."""
    
    def parse_output_xml(self, xml_path: Path) -> List[TestResult]:
        """Parse Robot Framework output.xml and extract test results."""
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            test_results = []
            
            for suite in root.findall('.//suite'):
                suite_source = suite.get('source', '')
                if not suite_source:
                    continue
                    
                file_path = Path(suite_source)
                
                for test in suite.findall('test'):
                    test_name = test.get('name', '')
                    if not test_name:
                        continue
                    
                    status_elem = test.find('status')
                    if status_elem is None:
                        continue
                    
                    status = status_elem.get('status', 'UNKNOWN')
                    elapsed = float(status_elem.get('elapsed', 0)) / 1000.0  # ms to seconds
                    
                    # Extract error message for failures
                    error_message = None
                    if status == 'FAIL':
                        msg_elem = status_elem.find('msg')
                        if msg_elem is not None and msg_elem.text:
                            error_message = msg_elem.text
                    
                    test_result = TestResult(
                        test_name=test_name,
                        file_path=file_path,
                        status=status,
                        execution_time=elapsed,
                        error_message=error_message,
                        timestamp=datetime.now()  # Could extract from XML if available
                    )
                    test_results.append(test_result)
            
            return test_results
            
        except Exception as e:
            raise ValueError(f"Failed to parse Robot Framework XML: {e}")
