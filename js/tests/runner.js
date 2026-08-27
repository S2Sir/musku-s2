/**
 * runner.js — Browser JS Test Runner for MUSKU Storage Engine
 */

(function () {
  'use strict';

  var passes = 0;
  var fails = 0;

  var assert = {
    ok: function (val, msg) {
      if (val) { passes++; console.log('  [PASS]', msg); }
      else { fails++; console.error('  [FAIL]', msg); }
    },
    equal: function (actual, expected, msg) {
      if (actual === expected) { passes++; console.log('  [PASS]', msg); }
      else { fails++; console.error('  [FAIL]', msg, '(Expected:', expected, 'Got:', actual, ')'); }
    }
  };

  // Node environment mock setup
  if (typeof window === 'undefined') {
    try {
      Object.defineProperty(globalThis, 'navigator', {
        value: {
          storage: {
            estimate: function () {
              return Promise.resolve({ usage: 12500000, quota: 50000000000 });
            }
          }
        },
        configurable: true,
        writable: true
      });
    } catch (e) {}

    var mockStores = ['conversations', 'messages', 'memory', 'user_profile', 'persona_state', 'projects', 'metadata'];
    globalThis.indexedDB = {
      open: function (name, version) {
        var req = { result: null, onupgradeneeded: null, onsuccess: null, onerror: null };
        setTimeout(function () {
          var db = {
            name: name,
            version: version,
            objectStoreNames: {
              contains: function (s) { return mockStores.indexOf(s) !== -1; }
            },
            createObjectStore: function () { return { createIndex: function () {} }; },
            transaction: function () {
              return {
                objectStore: function () {
                  return {
                    put: function (data) { var r = { onsuccess: null }; setTimeout(function(){ if(r.onsuccess) r.onsuccess(); }, 5); return r; },
                    getAll: function () { var r = { result: [], onsuccess: null }; setTimeout(function(){ if(r.onsuccess) r.onsuccess(); }, 5); return r; },
                    index: function () { return { getAll: function () { var r = { result: [], onsuccess: null }; setTimeout(function(){ if(r.onsuccess) r.onsuccess(); }, 5); return r; } }; }
                  };
                }
              };
            }
          };
          req.result = db;
          if (req.onupgradeneeded) req.onupgradeneeded({ target: { result: db } });
          if (req.onsuccess) req.onsuccess({ target: { result: db } });
        }, 10);
        return req;
      }
    };

    require('../storage/db.js');
    require('../storage/queue.js');
    require('../storage/backup.js');
    require('../storage/folder.js');

    var dbTest = require('./storage-db.test.js');
    var queueTest = require('./storage-queue.test.js');
    var backupTest = require('./backup-restore.test.js');
    var migrationTest = require('./migration.test.js');

    console.log('=== RUNNING MUSKU WEB STORAGE JS TEST SUITE ===');

    console.log('\n--- 1. Storage DB Tests ---');
    dbTest.testStorageDB(assert).then(function () {
      console.log('\n--- 2. Storage Queue Tests ---');
      queueTest.testStorageQueue(assert);

      console.log('\n--- 3. Backup & Restore Tests ---');
      backupTest.testBackupRestore(assert);

      console.log('\n--- 4. Migration Tests ---');
      migrationTest.testMigration(assert);

      console.log('\n===================================');
      console.log('RESULTS: Passed:', passes, '| Failed:', fails);
      if (fails > 0) process.exit(1);
    }).catch(function (err) {
      console.error('Test execution error:', err);
      process.exit(1);
    });
  }
})();
