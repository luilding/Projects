# from actions import ActionRunDirectionScript
# from rasa_sdk.executor import CollectingDispatcher
# from rasa_sdk import Tracker

# class TestDispatcher(CollectingDispatcher):
#     def __init__(self):
#         super().__init__()
    
#     def utter_message(self, **kwargs):
#         if 'text' in kwargs:
#             print("\nMessage sent to user:")
#             print(kwargs['text'])
#             print("-" * 50)

# class MockTracker:
#     def get_slot(self, slot_name):
#         if slot_name == 'location_from':
#             return 'Kensington'
#         elif slot_name == 'location_to':
#             return 'Fairfield'
#         return None

#     def get_latest_input_channel(self):
#         return "test"

# tracker = MockTracker()
# dispatcher = TestDispatcher()
# domain = {}

# print("\nStarting test...")
# print("Testing route from Kensington to Fairfield")
# print("=" * 50)

# action = ActionRunDirectionScript()
# print("\nRunning action...")
# action.run(dispatcher, tracker, domain)