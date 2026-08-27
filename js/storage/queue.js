/**
 * queue.js — Asynchronous Non-Blocking Storage Write Queue
 * Guarantees that storage operations NEVER block the realtime audio/voice path.
 */

(function (window) {
  'use strict';

  function StorageWriteQueue(dbInstance) {
    this.db = dbInstance || (window && window.muskuDB);
    this.queue = [];
    this.isProcessing = false;
  }

  StorageWriteQueue.prototype.enqueue = function (priority, actionType, payload) {
    this.queue.push({
      priority: priority || 0, // P0: Critical Chat, P1: Profile, P2: Memory, P3: Backup
      actionType: actionType,
      payload: payload,
      enqueuedAt: Date.now()
    });

    // Sort by priority (higher priority runs first)
    this.queue.sort(function (a, b) {
      return a.priority - b.priority;
    });

    this._scheduleFlush();
  };

  StorageWriteQueue.prototype._scheduleFlush = function () {
    var self = this;
    if (this.isProcessing || !this.queue.length) return;

    // Use requestIdleCallback or setTimeout to yield to UI/voice threads
    var defer = typeof window !== 'undefined' && window.requestIdleCallback
      ? window.requestIdleCallback
      : function (cb) { setTimeout(cb, 10); };

    defer(function () {
      self._processQueue();
    });
  };

  StorageWriteQueue.prototype._processQueue = function () {
    if (!this.queue.length) {
      this.isProcessing = false;
      return;
    }

    this.isProcessing = true;
    var task = this.queue.shift();
    var self = this;

    var promise = Promise.resolve();
    if (task.actionType === 'SAVE_MESSAGE') {
      promise = this.db ? this.db.saveMessage(task.payload) : Promise.resolve();
    } else if (task.actionType === 'SAVE_CONVERSATION') {
      promise = this.db ? this.db.saveConversation(task.payload) : Promise.resolve();
    }

    promise.then(function () {
      self.isProcessing = false;
      self._scheduleFlush();
    }).catch(function (err) {
      console.warn('[StorageWriteQueue] Non-blocking write retry log:', err);
      self.isProcessing = false;
      self._scheduleFlush();
    });
  };

  window.muskuStorageQueue = new StorageWriteQueue();
})(typeof window !== 'undefined' ? window : global);
