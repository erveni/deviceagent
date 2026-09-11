import unittest
from tools.chrome_low_cost_bootstrap import center_for_resource


class ChromeLowCostBootstrapTests(unittest.TestCase):
    def test_resource_center(self):
        xml='<node resource-id="com.android.chrome:id/negative_button" bounds="[20,100][220,200]" />'
        self.assertEqual(center_for_resource(xml,'com.android.chrome:id/negative_button'),(120,150))
        self.assertIsNone(center_for_resource(xml,'missing'))

    def test_android_compatibility_dialog_is_dismissible(self):
        xml='<node text="OK" resource-id="android:id/button1" bounds="[10,20][110,80]" />'
        self.assertEqual(center_for_resource(xml,'android:id/button1'),(60,50))


if __name__=='__main__':unittest.main()
