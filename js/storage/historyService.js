/* js/storage/historyService.js — LocalHistoryService (Single Writer for IndexedDB chat)
PRO Architecture: All browser chat history goes through this service.
- IndexedDB is Truth (local), Firestore is NOT used for normal chat
- UID-scoped, instant UI, async queue
*/
(function(){
  const DB_READY = () => window.muskuDB && window.muskuStorageQueue;

  function uidScopedId(prefix, uid){
    const u = (uid || localStorage.getItem('musku_anon_uid') || 'owner');
    return prefix + '_' + u + '_' + Date.now() + '_' + Math.random().toString(36).slice(2,6);
  }

  function todayKey(){
    const d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
  }

  window.LocalHistoryService = {
    save_message: function(role, content, opts){
      opts = opts || {};
      const k = opts.date_key || todayKey();
      const uid = opts.uid || null;
      const msg = {
        message_id: uidScopedId('msg', uid),
        conversation_id: 'conv_' + k + '_' + (uid || 'local'),
        role: role,
        content: String(content).slice(0, 2000),
        timestamp: Date.now(),
        date_key: k,
        sync_status: 'pending'
      };
      if(DB_READY()){
        window.muskuStorageQueue.enqueue(0, 'SAVE_MESSAGE', msg);
        window.muskuStorageQueue.enqueue(0, 'SAVE_CONVERSATION', {
          conversation_id: msg.conversation_id,
          date_key: k,
          created_at: msg.timestamp,
          last_message_preview: msg.content.slice(0,120)
        });
      }
      return msg;
    },
    load_conversation: async function(conversation_id){
      if(!window.muskuDB) return [];
      return window.muskuDB.getMessagesByConversation(conversation_id);
    },
    load_history: async function(date_key){
      if(!window.muskuDB) return [];
      const k = date_key || todayKey();
      // Fallback to localStorage for migration period
      try{
        const raw = JSON.parse(localStorage.getItem('musku_hist_' + k) || '[]');
        if(raw.length) return raw;
      }catch(e){}
      if(window.muskuDB.getMessagesByDate){
        return window.muskuDB.getMessagesByDate(k);
      }
      return [];
    },
    clear_history: async function(date_key){
      const k = date_key || todayKey();
      try{ localStorage.removeItem('musku_hist_' + k); }catch(e){}
      if(window.muskuDB && window.muskuDB.clearMessagesByDate){
        await window.muskuDB.clearMessagesByDate(k);
      }
      // Do NOT clear Firebase memory
    },
    clear_all_local: async function(){
      // Clear IndexedDB + localStorage chat, keep Firebase memory
      const days = JSON.parse(localStorage.getItem('musku_hist_days') || '[]');
      days.forEach(d=>{
        try{ localStorage.removeItem('musku_hist_' + d); }catch(e){}
      });
      try{ localStorage.removeItem('musku_hist_days'); }catch(e){}
      if(window.muskuDB && window.muskuDB.clearAll){
        await window.muskuDB.clearAll();
      }
    }
  };
})();
