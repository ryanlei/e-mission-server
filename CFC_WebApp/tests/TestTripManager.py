import unittest
import json
from utils import load_database_json, purge_database_json
from main import tripManager
from pymongo import MongoClient
import logging
from get_database import get_db, get_mode_db, get_section_db
import re
# Needed to modify the pythonpath
import sys
import os
from datetime import datetime, timedelta
from dao.user import User
from dao.client import Client
import tests.common

logging.basicConfig(level=logging.DEBUG)

class TestTripManager(unittest.TestCase):
  def setUp(self):
    self.testUsers = ["test@example.com", "best@example.com", "fest@example.com",
                      "rest@example.com", "nest@example.com"]
    self.serverName = 'localhost'

    # Sometimes, we may have entries left behind in the database if one of the tests failed
    # or threw an exception, so let us start by cleaning up all entries
    tests.common.dropAllCollections(get_db())
    self.ModesColl = get_mode_db()
    # self.ModesColl.remove()
    self.assertEquals(self.ModesColl.find().count(), 0)

    self.SectionsColl = get_section_db()
    # self.SectionsColl.remove()
    self.assertEquals(self.SectionsColl.find().count(), 0)

    load_database_json.loadTable(self.serverName, "Stage_Modes", "tests/data/modes.json")
    load_database_json.loadTable(self.serverName, "Stage_Sections", "tests/data/testCarbonFile")

    # Let's make sure that the users are registered so that they have profiles
    for userEmail in self.testUsers:
      User.register(userEmail)

    self.walkExpect = 1057.2524056424411
    self.busExpect = 2162.668467546699
    self.busCarbon = 267.0/1609

    self.now = datetime.now()
    self.dayago = self.now - timedelta(days=1)
    self.weekago = self.now - timedelta(weeks = 1)

    for section in self.SectionsColl.find():
      section['section_start_datetime'] = self.dayago
      section['section_end_datetime'] = self.dayago + timedelta(hours = 1)
      section['predicted_mode'] = [0, 0.4, 0.6, 0]
      section['confirmed_mode'] = ''
      # print("Section start = %s, section end = %s" %
      #   (section['section_start_datetime'], section['section_end_datetime']))
      # Replace the user email with the UUID
      section['user_id'] = User.fromEmail(section['user_id']).uuid
      self.SectionsColl.save(section)

  def tearDown(self):
    for testUser in self.testUsers:
      purge_database_json.purgeData('localhost', testUser)
    self.ModesColl.remove()
    self.assertEquals(self.ModesColl.find().count(), 0)

  def testQueryUnclassifiedSectionsWeekAgo(self):
    # Add some old sections that shouldn't be returned by the query
    # This one is just over a week old
    old_sec_1 = self.SectionsColl.find_one({'$and': [{'user_id': User.fromEmail('fest@example.com').uuid}, {'type':'move'}, {'mode':1}]})
    old_sec_1['_id'] = 'old_sec_1'
    old_sec_1['section_start_datetime'] = self.weekago - timedelta(minutes = 30)
    old_sec_1['section_end_datetime'] = self.weekago - timedelta(minutes = 5)
    logging.debug("Inserting old_sec_1 %s" % old_sec_1)
    self.SectionsColl.insert(old_sec_1)

    # This one is a month old
    monthago = self.now - timedelta(days = 30)
    old_sec_2 = self.SectionsColl.find_one({'$and': [{'user_id':User.fromEmail('fest@example.com').uuid}, {'type':'move'}, {'mode':4}]})
    old_sec_2['_id'] = 'old_sec_2'
    old_sec_2['section_start_datetime'] = monthago - timedelta(minutes = 30)
    old_sec_2['section_end_datetime'] = monthago - timedelta(minutes = 5)
    logging.debug("Inserting old_sec_2 %s" % old_sec_2)
    self.SectionsColl.insert(old_sec_2)

    # This one is missing the predicted mode
    monthago = self.now - timedelta(days = 30)
    un_pred_sec = self.SectionsColl.find_one({'$and': [{'user_id':User.fromEmail('fest@example.com').uuid}, {'type':'move'}, {'mode':4}]})
    un_pred_sec['_id'] = 'un_pred_sec'
    del un_pred_sec['predicted_mode']
    logging.debug("Inserting un_pred_sec %s" % un_pred_sec)
    self.SectionsColl.insert(un_pred_sec)

    queriedUnclassifiedSections = tripManager.queryUnclassifiedSections(User.fromEmail('fest@example.com').uuid)
    self.assertEqual(queriedUnclassifiedSections.count(), 2)

  def testQueryUnclassifiedSectionsLowConfidence(self):
    from dao.user import User

    fakeEmail = "fest@example.com"

    client = Client("testclient")
    client.update(createKey = False)
    tests.common.makeValid(client)

    (resultPre, resultReg) = client.preRegister("this_is_the_super_secret_id", fakeEmail)
    self.assertEqual(resultPre, 0)
    self.assertEqual(resultReg, 1)

    user = User.fromEmail(fakeEmail)
    self.assertEqual(user.getFirstStudy(), 'testclient')

    queriedUnclassifiedSections = tripManager.queryUnclassifiedSections(User.fromEmail(fakeEmail).uuid)
    self.assertEqual(queriedUnclassifiedSections.count(), 2)

    # Set the auto_confirmed values for the trips
    for section in queriedUnclassifiedSections:
      print section['_id']
      self.SectionsColl.update({'_id': section['_id']}, {'test_auto_confirmed': {'mode': section['mode'], 'prob': 0.95}})

    # Now, set the update timestamp to two weeks ago so that we will start filtering
    tests.common.updateUserCreateTime(user.uuid)
    queriedUnclassifiedSections = tripManager.queryUnclassifiedSections(User.fromEmail(fakeEmail).uuid)
    self.assertEqual(queriedUnclassifiedSections.count(), 0)

if __name__ == '__main__':
    unittest.main()
    
  
