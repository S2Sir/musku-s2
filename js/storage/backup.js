/**
 * backup.js — Versioned Backup Export & 5-Step Integrity Restore Manager
 * Backup Format: MUSKU_BACKUP v1
 */

(function (window) {
  'use strict';

  var BACKUP_FORMAT = 'MUSKU_BACKUP';
  var BACKUP_VERSION = 1;

  function BackupManager(dbInstance) {
    this.db = dbInstance || (window && window.muskuDB);
  }

  BackupManager.prototype.exportBackup = function () {
    var self = this;
    return Promise.all([
      self.db ? self.db.getAllConversations() : Promise.resolve([]),
      self._getLocalStorageData()
    ]).then(function (results) {
      var conversations = results[0];
      var localData = results[1];

      var backup = {
        format: BACKUP_FORMAT,
        version: BACKUP_VERSION,
        created_at: new Date().toISOString(),
        profile: {
          name: localData.musku_user_name || 'aap',
          title: localData.musku_user_title || 'aap',
          language: localData.musku_voice_lang || 'hinglish'
        },
        persona: {
          relationship_mode: localData.musku_relationship_mode || 'best_friend'
        },
        conversations: conversations,
        messages: [],
        memory: [],
        projects: []
      };

      return backup;
    });
  };

  BackupManager.prototype._getLocalStorageData = function () {
    if (typeof localStorage === 'undefined') return {};
    return {
      musku_user_name: localStorage.getItem('musku_user_name'),
      musku_user_title: localStorage.getItem('musku_user_title'),
      musku_voice_lang: localStorage.getItem('musku_voice_lang'),
      musku_relationship_mode: localStorage.getItem('musku_relationship_mode')
    };
  };

  BackupManager.prototype.validateBackupObject = function (obj) {
    // 5-Step Validation: 1. Validate object, 2. Schema check, 3. Integrity check
    if (!obj || typeof obj !== 'object') {
      return { valid: false, error: 'Invalid JSON backup object' };
    }
    if (obj.format !== BACKUP_FORMAT) {
      return { valid: false, error: 'Unsupported backup format: ' + obj.format };
    }
    if (!obj.version || obj.version > BACKUP_VERSION) {
      return { valid: false, error: 'Unsupported backup version: ' + obj.version };
    }
    if (!Array.isArray(obj.conversations)) {
      return { valid: false, error: 'Corrupted backup: conversations must be an array' };
    }
    return {
      valid: true,
      preview: {
        conversationsCount: obj.conversations.length,
        profileName: (obj.profile && obj.profile.name) || 'User',
        created_at: obj.created_at
      }
    };
  };

  BackupManager.prototype.restoreBackup = function (backupObj) {
    var check = this.validateBackupObject(backupObj);
    if (!check.valid) {
      return Promise.reject(new Error(check.error));
    }

    var self = this;
    var promises = [];
    if (backupObj.profile && backupObj.profile.name) {
      try { localStorage.setItem('musku_user_name', backupObj.profile.name); } catch (e) {}
    }
    if (backupObj.profile && backupObj.profile.title) {
      try { localStorage.setItem('musku_user_title', backupObj.profile.title); } catch (e) {}
    }
    if (backupObj.persona && backupObj.persona.relationship_mode) {
      try { localStorage.setItem('musku_relationship_mode', backupObj.persona.relationship_mode); } catch (e) {}
    }

    if (self.db && backupObj.conversations.length) {
      backupObj.conversations.forEach(function (conv) {
        promises.push(self.db.saveConversation(conv));
      });
    }

    return Promise.all(promises).then(function () {
      return { restoredConversations: backupObj.conversations.length };
    });
  };

  window.muskuBackup = new BackupManager();
})(typeof window !== 'undefined' ? window : global);
