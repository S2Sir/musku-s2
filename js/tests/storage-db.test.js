/**
 * storage-db.test.js — Unit tests for IndexedDB Primary Database Manager
 */

(function (exports) {
  'use strict';

  function testStorageDB(assert) {
    var db = globalThis.muskuDB;
    assert.ok(db, 'muskuDB instance should exist');

    return db.open().then(function (database) {
      assert.ok(database, 'IndexedDB database should open successfully');
      assert.equal(database.name, 'MUSKU_DB', 'Database name should be MUSKU_DB');
      assert.ok(database.objectStoreNames.contains('conversations'), 'conversations store should exist');
      assert.ok(database.objectStoreNames.contains('messages'), 'messages store should exist');
      assert.ok(database.objectStoreNames.contains('memory'), 'memory store should exist');

      return db.getStorageQuotaEstimate().then(function (estimate) {
        assert.ok(estimate.formatted, 'Quota estimate formatted string should exist');
      });
    });
  }

  exports.testStorageDB = testStorageDB;
})(typeof exports !== 'undefined' ? exports : globalThis);
