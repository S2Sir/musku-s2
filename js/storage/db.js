/**
 * db.js — IndexedDB Primary Database Manager for MUSKU Web (MUSKU_DB v1)
 * Primary local storage for conversations, messages, memory, profile, and persona states.
 */

(function (window) {
  'use strict';

  var DB_NAME = 'MUSKU_DB';
  var DB_VERSION = 1;

  function MUSKUDB() {
    this.db = null;
  }

  MUSKUDB.prototype.open = function () {
    var self = this;
    return new Promise(function (resolve, reject) {
      if (self.db) {
        return resolve(self.db);
      }
      var request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = function (event) {
        var db = event.target.result;

        // 1. Conversations store
        if (!db.objectStoreNames.contains('conversations')) {
          var convStore = db.createObjectStore('conversations', { keyPath: 'conversation_id' });
          convStore.createIndex('date_key', 'date_key', { unique: false });
          convStore.createIndex('created_at', 'created_at', { unique: false });
          convStore.createIndex('project_id', 'project_id', { unique: false });
        }

        // 2. Messages store
        if (!db.objectStoreNames.contains('messages')) {
          var msgStore = db.createObjectStore('messages', { keyPath: 'message_id' });
          msgStore.createIndex('conversation_id', 'conversation_id', { unique: false });
          msgStore.createIndex('timestamp', 'timestamp', { unique: false });
          msgStore.createIndex('role', 'role', { unique: false });
        }

        // 3. Memory store
        if (!db.objectStoreNames.contains('memory')) {
          var memStore = db.createObjectStore('memory', { keyPath: 'memory_id' });
          memStore.createIndex('category', 'category', { unique: false });
          memStore.createIndex('confidence', 'confidence', { unique: false });
        }

        // 4. User Profile store
        if (!db.objectStoreNames.contains('user_profile')) {
          db.createObjectStore('user_profile', { keyPath: 'key' });
        }

        // 5. Persona store
        if (!db.objectStoreNames.contains('persona_state')) {
          db.createObjectStore('persona_state', { keyPath: 'key' });
        }

        // 6. Projects store
        if (!db.objectStoreNames.contains('projects')) {
          db.createObjectStore('projects', { keyPath: 'project_id' });
        }

        // 7. Metadata store
        if (!db.objectStoreNames.contains('metadata')) {
          db.createObjectStore('metadata', { keyPath: 'key' });
        }
      };

      request.onsuccess = function (event) {
        self.db = event.target.result;
        resolve(self.db);
      };

      request.onerror = function (event) {
        reject(event.target.error);
      };
    });
  };

  MUSKUDB.prototype.saveMessage = function (msg) {
    var self = this;
    return this.open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(['messages'], 'readwrite');
        var store = tx.objectStore('messages');
        var req = store.put(msg);
        req.onsuccess = function () { resolve(msg); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  };

  MUSKUDB.prototype.getMessagesByConversation = function (conversationId) {
    return this.open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(['messages'], 'readonly');
        var store = tx.objectStore('messages');
        var index = store.index('conversation_id');
        var req = index.getAll(conversationId);
        req.onsuccess = function () {
          var msgs = req.result || [];
          msgs.sort(function (a, b) { return a.timestamp - b.timestamp; });
          resolve(msgs);
        };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  };

  MUSKUDB.prototype.saveConversation = function (conv) {
    return this.open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(['conversations'], 'readwrite');
        var store = tx.objectStore('conversations');
        var req = store.put(conv);
        req.onsuccess = function () { resolve(conv); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  };

  MUSKUDB.prototype.getConversationsByDate = function (dateKey) {
    return this.open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(['conversations'], 'readonly');
        var store = tx.objectStore('conversations');
        var index = store.index('date_key');
        var req = index.getAll(dateKey);
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  };

  MUSKUDB.prototype.getAllConversations = function () {
    return this.open().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(['conversations'], 'readonly');
        var store = tx.objectStore('conversations');
        var req = store.getAll();
        req.onsuccess = function () { resolve(req.result || []); };
        req.onerror = function (e) { reject(e.target.error); };
      });
    });
  };

  MUSKUDB.prototype.getStorageQuotaEstimate = function () {
    if (navigator.storage && navigator.storage.estimate) {
      return navigator.storage.estimate().then(function (estimate) {
        var usageMB = (estimate.usage / (1024 * 1024)).toFixed(2);
        var quotaMB = (estimate.quota / (1024 * 1024)).toFixed(2);
        return {
          usageBytes: estimate.usage,
          quotaBytes: estimate.quota,
          usageMB: usageMB,
          quotaMB: quotaMB,
          formatted: usageMB + ' MB used of ~' + quotaMB + ' MB quota'
        };
      });
    }
    return Promise.resolve({ formatted: 'Storage quota monitoring unavailable' });
  };

  window.muskuDB = new MUSKUDB();
})(typeof window !== 'undefined' ? window : global);
