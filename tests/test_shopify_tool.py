import unittest
from src.tools.ecommerce_shopify_tools import get_shopify_order_details

class TestShopifyTool(unittest.TestCase):
    def test_get_shopify_order_details(self):
        # This is a simple test to verify the tool can be imported and instantiated
        # In a real implementation, you would test with actual Shopify API calls
        self.assertTrue(callable(get_shopify_order_details))

if __name__ == '__main__':
    unittest.main()