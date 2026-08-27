/* MUSKU Auth — Firebase Google Sign-In + Plans (Free 7D once per ID + Pro) — alg file for easy samjh */
(function(){
  const CFG = {
    firebase: {
      apiKey: "AIzaSyDaVV9lTo86wWb0pDGB1voGdifxhFMPVdo",
      authDomain: "musku-ai.firebaseapp.com",
      databaseURL: "https://musku-ai-default-rtdb.firebaseio.com",
      projectId: "musku-ai",
      storageBucket: "musku-ai.firebasestorage.app",
      messagingSenderId: "1029490161907",
      appId: "1:1029490161907:web:d6e2ea8204dda0c3cadf86",
      measurementId: "G-RJ8ZP8WTX0"
    },
    useFirebase: true,
    adminEmails: ["s2sir5252@gmail.com"],
    adminUids: ["H4cxtamW96NJxl1doz2G9edi0O92"]
  };
  function isAdminUser(){
    try{
      var u=loadUser();
      if(!u) return false;
      if(CFG.adminUids.indexOf(u.uid)!==-1) return true;
      if(u.email && CFG.adminEmails.indexOf(u.email.toLowerCase())!==-1) return true;
      // also check Firebase currentUser
      if(typeof firebase!=="undefined" && firebase.apps.length && firebase.auth().currentUser){
        var fu=firebase.auth().currentUser;
        if(fu.email && CFG.adminEmails.indexOf(fu.email.toLowerCase())!==-1) return true;
        if(CFG.adminUids.indexOf(fu.uid)!==-1) return true;
      }
    }catch(e){}
    return false;
  }
  // ===== DEVICE + IP + LOCATION TRACE (admin trace) =====
  function getDeviceId(){
    try{
      var d=localStorage.getItem("musku_device_id");
      if(d) return d;
      var raw=(navigator.userAgent||"")+"|"+(navigator.language||"")+"|"+(screen.width+"x"+screen.height)+"|"+(Intl.DateTimeFormat().resolvedOptions().timeZone||"")+"|"+Date.now()+Math.random();
      var hash=0; for(var i=0;i<raw.length;i++){ hash=((hash<<5)-hash)+raw.charCodeAt(i); hash|=0; }
      d="dev-"+Math.abs(hash).toString(36)+"-"+Date.now().toString(36);
      localStorage.setItem("musku_device_id", d);
      return d;
    }catch(e){ return "dev-unknown-"+Date.now(); }
  }
  function getDeviceInfo(){
    try{
      return {
        deviceId: getDeviceId(),
        userAgent: navigator.userAgent||"",
        platform: navigator.platform||"",
        language: navigator.language||"",
        screen: (screen.width+"x"+screen.height),
        timezone: (Intl.DateTimeFormat().resolvedOptions().timeZone||""),
        onLine: navigator.onLine
      };
    }catch(e){ return { deviceId:getDeviceId() }; }
  }
  var _traceCache={ ip:null, loc:null, ipFetched:false };
  function fetchIP(){
    return new Promise(function(resolve){
      if(_traceCache.ipFetched) return resolve(_traceCache.ip);
      try{
        fetch("https://api.ipify.org?format=json",{cache:"no-store"}).then(function(r){return r.json();}).then(function(j){
          _traceCache.ip=j.ip||null; _traceCache.ipFetched=true; resolve(_traceCache.ip);
        }).catch(function(){ _traceCache.ipFetched=true; resolve(null); });
        setTimeout(function(){ if(!_traceCache.ipFetched){ _traceCache.ipFetched=true; resolve(null);} }, 2500);
      }catch(e){ resolve(null); }
    });
  }
  function requestLocation(){
    return new Promise(function(resolve){
      if(_traceCache.loc) return resolve(_traceCache.loc);
      if(!navigator.geolocation) return resolve(null);
      var opts={ enableHighAccuracy:true, timeout:7000, maximumAge:60000 };
      navigator.geolocation.getCurrentPosition(function(pos){
        var v={ lat:pos.coords.latitude, lng:pos.coords.longitude, accuracy:pos.coords.accuracy, timestamp:new Date().toISOString() };
        try{ localStorage.setItem("musku_last_loc", JSON.stringify(v)); }catch(e){}
        _traceCache.loc=v; resolve(v);
      }, function(err){
        try{ var prev=localStorage.getItem("musku_last_loc"); if(prev) _traceCache.loc=JSON.parse(prev); }catch(e){}
        resolve(_traceCache.loc||null);
      }, opts);
    });
  }
  function safeEmailKey(email){
    if(!email) return null;
    // Firebase keys cannot contain . # $ [ ] / — replace . with ,
    return email.toLowerCase().replace(/\./g, ",").replace(/\$/g,"_").replace(/\#/g,"_").replace(/\[/g,"_").replace(/\]/g,"_").replace(/\//g,"_");
  }
  function collectAndStoreTrace(reason){
    var uid=getCurrentUid();
    if(!uid) return;
    var dev=getDeviceInfo();
    Promise.all([fetchIP(), requestLocation()]).then(function(vals){
      var ip=vals[0], loc=vals[1];
      var email=(loadUser()&&loadUser().email)||"";
      var payload={
        uid:uid,
        email:email,
        reason: reason||"active",
        deviceId: dev.deviceId,
        userAgent: dev.userAgent,
        platform: dev.platform,
        language: dev.language,
        screen: dev.screen,
        timezone: dev.timezone,
        ip: ip||null,
        location: loc||null,
        url: location.href,
        timestamp: new Date().toISOString()
      };
      try{ localStorage.setItem("musku_trace_"+uid, JSON.stringify(payload)); }catch(e){}
      try{
        if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
          var base="musku_traces/"+uid;
          firebase.database().ref(base).set(payload).catch(function(){});
          // also keep user summary by UID
          firebase.database().ref("musku_users/"+uid).set({
            uid:uid, email:payload.email, deviceId:dev.deviceId, ip:ip, location:loc,
            lastSeen: payload.timestamp, lastReason: reason||"active", userAgent:dev.userAgent
          }).catch(function(){});
          // Gmail-index for easy admin search (ID ki jagah Gmail dikhega)
          var ek=safeEmailKey(email);
          if(ek){
            firebase.database().ref("musku_users_by_email/"+ek).set({
              uid:uid, email:email, deviceId:dev.deviceId, ip:ip, location:loc,
              lastSeen: payload.timestamp, lastReason: reason||"active"
            }).catch(function(){});
            firebase.database().ref("musku_email_index/"+ek).set(uid).catch(function(){});
          }
        }
      }catch(e){}
    }).catch(function(){});
  }
  // ===== ID TOKEN cache for backend auth verification =====
  function refreshMuskuToken(){
    try{
      if(typeof firebase!=="undefined" && firebase.apps.length && firebase.auth().currentUser){
        firebase.auth().currentUser.getIdToken(true).then(function(tok){
          try{ localStorage.setItem("musku_id_token", tok); }catch(e){}
        }).catch(function(){});
      }
    }catch(e){}
  }
  // auto request location permission early (once per session)
  try{
    document.addEventListener("DOMContentLoaded", function(){
      refreshMuskuToken();
      try{ setInterval(refreshMuskuToken, 50*60*1000); }catch(e){} // refresh every 50 min (token ~1h)
      // warm up trace after 1.2s (non-blocking)
      setTimeout(function(){ try{ if(getCurrentUid()){ requestLocation(); fetchIP(); } }catch(e){} }, 1200);
    });
  }catch(e){}

  const LS_USER = "musku_auth_user";
  const LS_PLAN = "musku_activate_plan";
  const LS_GAME_USED = "musku_game_free_used"; // {"MUSKU-USER-1": true}
  const LS_GAME_ID = "musku_game_id";

  function toast(msg, ms){
    var el=document.getElementById("toast");
    if(!el) return;
    el.textContent=msg;
    el.classList.add("show");
    setTimeout(function(){ el.classList.remove("show"); }, ms||2400);
  }
  function uid(){ return "FREE-S2"; }
  function saveUser(u){
    try{ localStorage.setItem(LS_USER, JSON.stringify(u)); }catch(e){}
  }
  function loadUser(){
    try{ return JSON.parse(localStorage.getItem(LS_USER)||"null"); }catch(e){ return null; }
  }
  function savePlan(p){
    try{
      localStorage.setItem(LS_PLAN, JSON.stringify(p));
      var uid=getCurrentUid();
      if(uid) try{ localStorage.setItem(LS_PLAN+"_"+uid, JSON.stringify(p)); }catch(e){}
    }catch(e){}
  }
  function loadPlan(){
    try{
      var uid=getCurrentUid();
      if(uid){
        var per=localStorage.getItem(LS_PLAN+"_"+uid);
        if(per) return JSON.parse(per);
      }
      return JSON.parse(localStorage.getItem(LS_PLAN)||"null");
    }catch(e){ return null; }
  }
  function getCurrentUid(){
    try{
      var u=loadUser();
      if(u && u.uid) return u.uid;
      if(typeof firebase!=="undefined" && firebase.apps.length){
        var fu=firebase.auth().currentUser;
        if(fu && fu.uid) return fu.uid;
      }
    }catch(e){}
    return null;
  }
  function isFreeUsed(gameId){
    if(!gameId) return false;
    gameId=gameId.trim().toUpperCase();
    // 1) Per Firebase Gmail UID check (1 ID = 1 Free) — new Gmail ko global se block nahi karna
    var uid=getCurrentUid();
    if(uid){
      try{
        if(localStorage.getItem("musku_free_claimed_"+uid)==="1") return true;
        if(localStorage.getItem("musku_free_claimed_fb_"+uid)==="1") return true;
        // Authenticated Gmail ke liye global check nahi — sirf per UID, nahi to new Gmail galat block hoga
        return false;
      }catch(e){ return false; }
    }
    // 2) Fallback global check (Guest / no UID — old local)
    try{
      var m=JSON.parse(localStorage.getItem(LS_GAME_USED)||"{}");
      return !!m[gameId];
    }catch(e){ return false; }
  }
  function markFreeUsed(gameId){
    if(!gameId) return;
    gameId=gameId.trim().toUpperCase();
    try{
      var m=JSON.parse(localStorage.getItem(LS_GAME_USED)||"{}");
      m[gameId]=true;
      localStorage.setItem(LS_GAME_USED, JSON.stringify(m));
      localStorage.setItem(LS_GAME_ID, gameId);
      var uid2=getCurrentUid();
      if(uid2){
        try{ localStorage.setItem("musku_free_claimed_"+uid2, "1"); }catch(e){}
        // Also push to Firebase Realtime DB for cross-device 1 Gmail = 1 Free (exact time)
        try{
          var _untilStore=new Date(Date.now()+7*24*3600*1000).toISOString();
          if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
            var ref=firebase.database().ref("freeClaims/"+uid2);
            ref.set({ claimed:true, gameId:gameId, at:new Date().toISOString(), until:_untilStore, email:(loadUser()&&loadUser().email)||"" });
          } else if(typeof firebase!=="undefined" && firebase.apps.length){
            // Fallback REST with ID token
            var fu3=firebase.auth().currentUser;
            if(fu3){
              fu3.getIdToken(false).then(function(tok){
                fetch("https://musku-ai-default-rtdb.firebaseio.com/freeClaims/"+encodeURIComponent(uid2)+".json?auth="+tok, { method:"PUT", body: JSON.stringify({ claimed:true, gameId:gameId, at:new Date().toISOString(), until:_untilStore }), headers:{ "Content-Type":"application/json"} }).catch(function(){});
              }).catch(function(){});
            }
          }
          // Also save exact until locally for plan expiry
          try{ localStorage.setItem("musku_free_until_"+uid2, _untilStore); }catch(e){}
        }catch(e){}
      }
    }catch(e){}
  }
  // Async Firebase check — 1 Gmail = 1 Free (cross-device)
  function checkFreeClaimedFirebase(){
    return new Promise(function(resolve){
      var uid=getCurrentUid();
      if(!uid) return resolve(false);
      // If already locally marked, true
      try{ if(localStorage.getItem("musku_free_claimed_"+uid)==="1") return resolve(true); }catch(e){}
      try{
        if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
          firebase.database().ref("freeClaims/"+uid).once("value").then(function(snap){
            var v=snap.val();
            var claimed=!!(v && v.claimed);
            if(claimed) try{ localStorage.setItem("musku_free_claimed_fb_"+uid,"1"); }catch(e){}
            resolve(claimed);
          }).catch(function(){ resolve(false); });
          return;
        }
        // Fallback REST
        var fu=firebase.auth().currentUser;
        if(fu){
          fu.getIdToken(false).then(function(tok){
            fetch("https://musku-ai-default-rtdb.firebaseio.com/freeClaims/"+encodeURIComponent(uid)+".json?auth="+tok).then(function(r){ return r.json(); }).then(function(val){
              var claimed=!!(val && val.claimed);
              if(claimed) try{ localStorage.setItem("musku_free_claimed_fb_"+uid,"1"); }catch(e){}
              resolve(claimed);
            }).catch(function(){ resolve(false); });
          }).catch(function(){ resolve(false); });
          return;
        }
      }catch(e){}
      resolve(false);
    });
  }

  // Sync active free plan from Firebase for cross-device access (exact time)
  function syncFreePlanFromFirebase(){
    var uid=getCurrentUid();
    if(!uid) return;
    try{
      if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
        firebase.database().ref("freeClaims/"+uid).once("value").then(function(snap){
          var v=snap.val();
          if(v && v.claimed && v.until){
            var exp=new Date(v.until).getTime();
            if(!isNaN(exp) && exp > Date.now()){
              var cur=loadPlan();
              if(!cur || !isPlanActive(cur)){
                savePlan({ type:"free", gameId:"FREE-S2", since:v.at||new Date().toISOString(), until:v.until });
                try{ localStorage.setItem("musku_free_claimed_"+uid,"1"); localStorage.setItem("musku_free_claimed_fb_"+uid,"1"); }catch(e){}
                try{ if(typeof renderPlan==="function" && typeof selectedPlan!=="undefined") renderPlan(selectedPlan); }catch(e){}
              }
            }
          }
        }).catch(function(){});
      }
    }catch(e){}
  }
  // ===== SECURE ACTIVATION KEY SYSTEM (Pro) — Firebase hidden, MUSKU branded =====
  var LS_ACT_KEY = "musku_activation_key";
  var LS_ACT_META = "musku_activation_meta";
  function genSecureKey(){
    // Pro: MUSKU- + 24 char base32 (A-Z2-7) = 120-bit, opaque, full CSPRNG, no Math.random fallback
    var alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
    var out="MUSKU-";
    var cryptoObj = (window.crypto||window.msCrypto);
    if(!cryptoObj || !cryptoObj.getRandomValues) throw new Error("Secure crypto unavailable");
    var bytes=new Uint8Array(18); // 144 bit -> 24*5 + padding
    cryptoObj.getRandomValues(bytes);
    var val=0, bits=0, count=0;
    for(var i=0;i<bytes.length;i++){
      val=(val<<8)|bytes[i]; bits+=8;
      while(bits>=5){
        bits-=5;
        var idx=(val>>bits)&31;
        out+=alphabet[idx];
        count++;
        if(count%4===0 && count<24) out+="-";
        if(count>=24) break;
      }
      if(count>=24) break;
    }
    return out; // MUSKU-XXXX-XXXX-XXXX-XXXX-XXXX 24 char (120-bit)
  }
  function getPlanDurationDays(type, tenure){
    if(type==="free") return 7;
    if(type==="pro"){
      if(tenure==="1m") return 30;
      if(tenure==="3m") return 90;
      if(tenure==="1y") return 365;
      return 30;
    }
    return 7;
  }
  // Pro helpers: SHA256 hex (sync), HMAC, rate-limit
  function sha256Hex(str){
    // minimal sync SHA256 (public domain) - 120-bit key hash, HMAC-style
    function rotr(n,x){ return (x >>> n) | (x << (32-n)); }
    function sigma0(x){ return rotr(7,x) ^ rotr(18,x) ^ (x>>>3); }
    function sigma1(x){ return rotr(17,x) ^ rotr(19,x) ^ (x>>>10); }
    function Sigma0(x){ return rotr(2,x) ^ rotr(13,x) ^ rotr(22,x); }
    function Sigma1(x){ return rotr(6,x) ^ rotr(11,x) ^ rotr(25,x); }
    function Ch(x,y,z){ return (x & y) ^ (~x & z); }
    function Maj(x,y,z){ return (x & y) ^ (x & z) ^ (y & z); }
    var K=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    var H=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    var msg=unescape(encodeURIComponent(str)); var l=msg.length; var bl=l*8;
    var bytes=[]; for(var i=0;i<l;i++) bytes.push(msg.charCodeAt(i));
    bytes.push(0x80); while((bytes.length%64)!==56) bytes.push(0);
    for(var i=7;i>=0;i--) bytes.push((bl>>> (i*8)) & 0xFF);
    // Note: for long keys (>55 bytes) padding简化 but MUSKU key ~29 bytes <55 so single block enough (pro key 29)
    if(bytes.length>64){ // fallback for longer (rare)
      // split into 64-byte blocks generic (only first block needed for 29-byte key, but keep correct for safety)
      var HB=H.slice(); var off=0;
      while(off<bytes.length){
        var W=[]; for(var t=0;t<16;t++){ W[t]=(bytes[off+t*4]<<24)|(bytes[off+t*4+1]<<16)|(bytes[off+t*4+2]<<8)|bytes[off+t*4+3]; }
        for(var t2=16;t2<64;t2++){ W[t2]= (sigma1(W[t2-2])+W[t2-7]+sigma0(W[t2-15])+W[t2-16])>>>0; }
        var a=HB[0],b=HB[1],c=HB[2],d=HB[3],e=HB[4],f=HB[5],g=HB[6],h=HB[7];
        for(var t3=0;t3<64;t3++){ var T1=(h+Sigma1(e)+Ch(e,f,g)+K[t3]+W[t3])>>>0; var T2=(Sigma0(a)+Maj(a,b,c))>>>0; h=g; g=f; f=e; e=(d+T1)>>>0; d=c; c=b; b=a; a=(T1+T2)>>>0; }
        HB[0]=(HB[0]+a)>>>0; HB[1]=(HB[1]+b)>>>0; HB[2]=(HB[2]+c)>>>0; HB[3]=(HB[3]+d)>>>0; HB[4]=(HB[4]+e)>>>0; HB[5]=(HB[5]+f)>>>0; HB[6]=(HB[6]+g)>>>0; HB[7]=(HB[7]+h)>>>0;
        off+=64;
      }
      H=HB;
    } else {
      var W=[]; for(var t=0;t<16;t++){ W[t]=(bytes[t*4]<<24)|(bytes[t*4+1]<<16)|(bytes[t*4+2]<<8)|bytes[t*4+3]; }
      for(var t2=16;t2<64;t2++){ W[t2]= (sigma1(W[t2-2])+W[t2-7]+sigma0(W[t2-15])+W[t2-16])>>>0; }
      var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
      for(var t3=0;t3<64;t3++){ var T1=(h+Sigma1(e)+Ch(e,f,g)+K[t3]+W[t3])>>>0; var T2=(Sigma0(a)+Maj(a,b,c))>>>0; h=g; g=f; f=e; e=(d+T1)>>>0; d=c; c=b; b=a; a=(T1+T2)>>>0; }
      H[0]=(H[0]+a)>>>0; H[1]=(H[1]+b)>>>0; H[2]=(H[2]+c)>>>0; H[3]=(H[3]+d)>>>0; H[4]=(H[4]+e)>>>0; H[5]=(H[5]+f)>>>0; H[6]=(H[6]+g)>>>0; H[7]=(H[7]+h)>>>0;
    }
    var hex=""; for(var i=0;i<H.length;i++){ var v=H[i]; for(var j=3;j>=0;j--){ var b=(v>>>(j*8))&0xFF; hex+= (b<16?"0":"")+b.toString(16); } }
    return hex;
  }
  var MUSKU_HMAC_SECRET="musku_pro_secret_2026_v1";
  function hmacForHash(hashHex){ return sha256Hex(MUSKU_HMAC_SECRET+":"+hashHex); }
  function isKeyVerifyRateLimited(){
    try{
      var k="musku_key_verify_attempts"; var now=Date.now(); var arr=JSON.parse(localStorage.getItem(k)||"[]");
      arr=arr.filter(function(t){ return now - t < 5*60*1000; });
      if(arr.length>=5) return true;
      arr.push(now); localStorage.setItem(k, JSON.stringify(arr)); return false;
    }catch(e){ return false; }
  }
  function storeActivationKey(key, meta){
    try{
      localStorage.setItem(LS_ACT_KEY, key);
      localStorage.setItem(LS_ACT_META, JSON.stringify(meta));
      var uid=getCurrentUid();
      if(uid){
        try{ localStorage.setItem(LS_ACT_KEY+"_"+uid, key); localStorage.setItem(LS_ACT_META+"_"+uid, JSON.stringify(meta)); }catch(e){}
      }
    }catch(e){}
    // Firebase hidden store — branded path, Pro: hash opaque (MUSKU- prefix se plan leak nahi) + HMAC
    try{
      var uid2=getCurrentUid();
      if(uid2 && typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
        var until=meta.until;
        var hashHex=""; var hmac=""; try{ hashHex=sha256Hex(key); hmac=hmacForHash(hashHex); }catch(e){}
        var payload={ uid:uid2, email:(loadUser()&&loadUser().email)||"", planType:meta.planType, tenure:meta.tenure||meta.planType, key:key, keyHash: hashHex, hmac: hmac, createdAt:meta.since||new Date().toISOString(), until:until, active:true };
        // Pro: global lookup by hash (opaque, raw never as path) + legacy plain for migration
        if(hashHex) firebase.database().ref("musku_keys_hash/"+hashHex).set(payload).catch(function(){});
        firebase.database().ref("musku_keys/"+key.replace(/\//g,"_")).set(payload).catch(function(){});
        // per-user current activation (cross-device sync)
        firebase.database().ref("musku_activations/"+uid2).set(payload).catch(function(){});
        // Gmail-index for easy search (ID ki jagah Gmail)
        try{
          var ek2=safeEmailKey(payload.email);
          if(ek2){
            firebase.database().ref("musku_activations_by_email/"+ek2).set(payload).catch(function(){});
            firebase.database().ref("freeClaims_by_email/"+ek2).set({ claimed:true, gameId:"FREE-S2", at:payload.createdAt, until:until, email:payload.email, key:key, uid:uid2 }).catch(function(){});
          }
        }catch(e){}
        // legacy freeClaims sync for backward compat
        if(meta.planType==="free"){
          try{ firebase.database().ref("freeClaims/"+uid2).set({ claimed:true, gameId:"FREE-S2", at:payload.createdAt, until:until, email:payload.email, key:key }); }catch(e){}
        }
      }
    }catch(e){}
  }
  function createAndStoreActivationKey(planType, tenure){
    // Pro keys only admin can generate — free trial allowed for self
    if(planType==="pro" && !isAdminUser()){
      try{ toast("Pro activation only via Admin — contact support"); }catch(e){}
      return null;
    }
    var days=getPlanDurationDays(planType, tenure);
    var now=new Date();
    var until=new Date(now.getTime()+days*24*3600*1000).toISOString();
    var key=genSecureKey();
    var meta={ planType:planType, tenure:tenure, since:now.toISOString(), until:until, days:days, key:key };
    storeActivationKey(key, meta);
    // trace every key creation (admin audit)
    try{ collectAndStoreTrace("key_create_"+planType+"_"+tenure); }catch(e){}
    return { key:key, meta:meta };
  }
  function lookupActivationKeyRemote(key){
    return new Promise(function(resolve){
      var k=(key||"").trim().toUpperCase();
      if(!k) return resolve(null);
      if(isKeyVerifyRateLimited()){
        return resolve({ __rateLimited:true });
      }
      var hashHex=""; var hmac=""; try{ hashHex=sha256Hex(k); hmac=hmacForHash(hashHex); }catch(e){}
      function isValidPayload(v){
        if(!v || !v.until) return false;
        var exp=new Date(v.until).getTime();
        if(isNaN(exp) || exp <= Date.now()) return false;
        // Pro HMAC verify if present (hash-based keys)
        if(hashHex && v.keyHash && v.keyHash!==hashHex) return false;
        if(hashHex && v.hmac && hmac && v.hmac!==hmac) return false;
        // maxUses check (if present)
        if(v.maxUses && v.usedCount>=v.maxUses && v.uid && v.uid!==getCurrentUid()) return false;
        return true;
      }
      try{
        if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
          // Pro path: hash lookup first (opaque, MUSKU- prefix leak nahi)
          if(hashHex){
            firebase.database().ref("musku_keys_hash/"+hashHex).once("value").then(function(snap){
              var v=snap.val();
              if(isValidPayload(v)) return resolve(v);
              // fallback plain (migration for old 16-char keys)
              firebase.database().ref("musku_keys/"+k).once("value").then(function(snap2){
                var v2=snap2.val();
                if(isValidPayload(v2)) return resolve(v2);
                resolve(null);
              }).catch(function(){ resolve(null); });
            }).catch(function(){
              firebase.database().ref("musku_keys/"+k).once("value").then(function(snap2){
                var v2=snap2.val();
                if(isValidPayload(v2)) return resolve(v2);
                resolve(null);
              }).catch(function(){ resolve(null); });
            });
            return;
          }
          firebase.database().ref("musku_keys/"+k).once("value").then(function(snap){
            var v=snap.val();
            if(isValidPayload(v)) return resolve(v);
            resolve(null);
          }).catch(function(){ resolve(null); });
          return;
        }
      }catch(e){}
      resolve(null);
    });
  }
  function activateWithKeyData(key, data){
    // data = { planType, tenure, until, since, key }
    var planType=data.planType||"free";
    var tenure=data.tenure||planType;
    var until=data.until;
    var since=data.since||new Date().toISOString();
    try{ collectAndStoreTrace("activate_"+planType+"_"+tenure); }catch(e){}
    if(planType==="free"){
      savePlan({ type:"free", gameId:"FREE-S2", since:since, until:until, activationKey:key });
    } else {
      var price = tenure==="1y" ? "₹999 / year" : tenure==="3m" ? "₹199 / 3 months" : "₹99 / month";
      savePlan({ type:"pro", tenure:tenure, price:price, since:since, until:until, activationKey:key });
    }
    // also store locally for display
    try{
      storeActivationKey(key, { planType:planType, tenure:tenure, since:since, until:until, key:key });
    }catch(e){}
    return true;
  }
  function syncActivationFromFirebase(){
    var uid=getCurrentUid();
    if(!uid) return;
    try{
      if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
        firebase.database().ref("musku_activations/"+uid).once("value").then(function(snap){
          var v=snap.val();
          if(v && v.key && v.until){
            var exp=new Date(v.until).getTime();
            if(!isNaN(exp) && exp > Date.now()){
              var cur=loadPlan();
              if(!cur || !isPlanActive(cur)){
                activateWithKeyData(v.key, v);
                try{ localStorage.setItem(LS_ACT_KEY+"_"+uid, v.key); }catch(e){}
                 try{ if(typeof renderPlan==="function" && typeof selectedPlan!=="undefined") renderPlan(selectedPlan); }catch(e){}
               }
            }
          }
        }).catch(function(){});
      }
    }catch(e){}
  }

  // Admin helper — ADMIN ONLY (bypass blocked for normal users)
  window.resetFreeForCurrentGmail=function(){
    if(!isAdminUser()){ console.warn("Admin only — access denied"); try{ toast("Admin only"); }catch(e){} return; }
    var uid=getCurrentUid();
    if(!uid){ console.log("No Gmail UID found — pehle Google se login karo"); return; }
    try{ localStorage.removeItem("musku_free_claimed_"+uid); localStorage.removeItem("musku_free_claimed_fb_"+uid); localStorage.removeItem(LS_PLAN+"_"+uid); localStorage.removeItem(LS_PLAN); localStorage.removeItem(LS_GAME_ID); localStorage.removeItem(LS_ACT_KEY+"_"+uid); localStorage.removeItem(LS_ACT_META+"_"+uid); localStorage.removeItem(LS_ACT_KEY); localStorage.removeItem(LS_ACT_META); }catch(e){}
    try{
      if(typeof firebase!=="undefined" && firebase.apps.length && firebase.database){
        firebase.database().ref("freeClaims/"+uid).remove().catch(function(){});
        firebase.database().ref("musku_activations/"+uid).remove().catch(function(){});
        // note: musku_keys/{oldKey} cleanup needs key value — try read then remove
        try{
          var oldK=localStorage.getItem(LS_ACT_KEY+"_"+uid)||localStorage.getItem(LS_ACT_KEY);
          if(oldK) firebase.database().ref("musku_keys/"+oldK).remove().catch(function(){});
        }catch(e){}
        console.log("Firebase activations cleared for",uid);
      }
    }catch(e){}
    console.log("Reset done for UID:",uid,"— refresh karo, Free 7D wapas active dikhega");
    try{ location.reload(); }catch(e){}
  };
  window.generateActivationKeyForCurrentPlan=function(planType, tenure){
    if(!isAdminUser()){ console.warn("Admin only — access denied"); try{ toast("Admin only — key generation blocked"); }catch(e){} return null; }
    var pt=planType||"pro", tn=tenure||"1m";
    var r=createAndStoreActivationKey(pt, tn);
    if(!r){ console.warn("Key generation blocked"); return null; }
    console.log("Generated key:", r.key, "meta:", r.meta);
    return r.key;
  };
  function confettiBurst(){
    var cols=["#c084fc","#f48fb1","#fde68a","#22d3ee","#43e97b"];
    for(var i=0;i<18;i++){
      var s=document.createElement("span");
      s.className="confetti";
      s.style.left=(40+Math.random()*60)+"vw";
      s.style.top="42%";
      s.style.background=cols[i%cols.length];
      s.style.transform="translateY(0) rotate("+Math.random()*360+"deg)";
      s.style.animationDelay=(Math.random()*0.2).toFixed(2)+"s";
      document.body.appendChild(s);
      (function(el){ setTimeout(function(){ el.remove(); }, 1200); })(s);
    }
  }

  // Firebase init (if enabled and keys filled)
  var fbApp=null, fbAuth=null;
  function initFirebase(){
    if(!CFG.useFirebase) return null;
    if(CFG.firebase.apiKey==="YOUR_API_KEY") {
      console.warn("MUSKU Auth: Firebase config placeholder — set useFirebase:false for demo or fill real keys");
      return null;
    }
    try{
      if(!firebase.apps.length) fbApp=firebase.initializeApp(CFG.firebase);
      else fbApp=firebase.app();
      fbAuth=firebase.auth();
      return fbAuth;
    }catch(e){ console.warn("Firebase init fail", e); return null; }
  }

  function goActivate(){
    location.replace("activate.html");
  }
  function goApp(){
    location.replace("index.html");
  }
  function goSignup(){
    location.replace("signup.html");
  }

  // SIGNUP page — Real Google Sign-In only (Demo/Guest removed)
  function initSignup(){
    var btn=document.getElementById("googleBtn");
    if(!btn) return;
    var auth=initFirebase();
    var u=loadUser();
    if(u && u.plan) { // already activated
      goActivate();
      return;
    }

    btn.addEventListener("click", function(){
      btn.disabled=true; btn.textContent="Signing in…";
      if(auth){
        var provider=new firebase.auth.GoogleAuthProvider();
        auth.signInWithPopup(provider).then(function(res){
          var fu=res.user;
          var nu={ uid:fu.uid, displayName:fu.displayName||"Boss", email:fu.email||"", photo:fu.photoURL||"", provider:"google" };
          saveUser(nu);
          try{ fu.getIdToken(true).then(function(tok){ try{ localStorage.setItem("musku_id_token", tok); }catch(e){} }).catch(function(){}); }catch(e){}
          try{ setTimeout(function(){ collectAndStoreTrace("login"); }, 600); }catch(e){}
          goActivate();
        }).catch(function(err){
          btn.disabled=false; btn.textContent="Continue with Google";
          toast((err&&err.message)||"Sign-in failed — please try again");
        });
      } else {
        btn.disabled=false; btn.textContent="Continue with Google";
        toast("Firebase not configured — please contact support");
      }
    });
  }

  // ACTIVATE page — Firebase enforced (instant click, non-blocking auth)
  function initActivate(){
    var u=loadUser();
    if(!u){ goSignup(); return; }
    var badge=document.getElementById("userBadge");
    if(badge){ badge.textContent=""; badge.style.display="none"; }
    // instant block for old guest/mock — no delay
    if(u && (u.provider==="guest" || u.provider==="mock")){
      try{ localStorage.removeItem(LS_USER); }catch(e){}
      goSignup();
      return;
    }
    // Firebase auth verify — async, never blocks UI wiring (race-safe: transient null ko ignore karo)
    if(CFG.useFirebase){
      try{
        var fbAuthChk=initFirebase();
        if(fbAuthChk){
          if(fbAuthChk.currentUser){
            var lu2=loadUser();
            if(!lu2 || lu2.uid !== fbAuthChk.currentUser.uid){
              var fu2=fbAuthChk.currentUser;
              saveUser({ uid:fu2.uid, displayName:fu2.displayName||"Boss", email:fu2.email||"", photo:fu2.photoURL||"", provider:"google" });
              u=loadUser();
            }
          } else {
            // currentUser null = Firebase abhi session restore kar raha hai -> turant redirect MAT karo
            var _resolved=false;
            var _timer=setTimeout(function(){
              if(_resolved) return;
              _resolved=true;
              try{
                if(!fbAuthChk.currentUser){
                  var uu=loadUser();
                  // local me valid google user hai to redirect skip (Firebase thoda late bhi ho)
                  if(!uu || uu.provider!=="google") goSignup();
                }
              }catch(e){}
            }, 1800);
            fbAuthChk.onAuthStateChanged(function(fbUser){
              if(_resolved) return;
              if(fbUser){
                _resolved=true;
                clearTimeout(_timer);
                var lu=loadUser();
                if(!lu || lu.uid !== fbUser.uid){
                  saveUser({ uid:fbUser.uid, displayName:fbUser.displayName||"Boss", email:fbUser.email||"", photo:fbUser.photoURL||"", provider:"google" });
                }
              }
              // fbUser null -> still waiting, timer decide karega (no instant removeItem)
            });
          }
        }
      }catch(e){}
    }

    var gameIn=document.getElementById("gameIdInput");
    var gameWrap=document.getElementById("gameIdWrap");
    var fundedBadge=document.getElementById("fundedBadge");
    var fundedName=document.getElementById("fundedName");
    var fundedDesc=document.getElementById("fundedDesc");
    var fundedPriceRow=document.getElementById("fundedPriceRow");
    var fundedFeats=document.getElementById("fundedFeats");
    var fundedCta=document.getElementById("fundedCta");
    var freeHint=document.getElementById("freeHint");
    var logoutBtn=document.getElementById("logoutBtn");
    var plan=loadPlan();
    // legacy compat: freeBtn/proBtn may not exist in funded design
    var freeBtn=document.getElementById("freeBtn");
    var proBtn=document.getElementById("proBtn");
    var priceLabel=document.getElementById("proPriceLabel");
    // --- MIGRATION: purana bug FREE-S2 ko FREE-S2 me correct karo ---
    try{
      var _gidFix=localStorage.getItem(LS_GAME_ID);
      if(_gidFix && _gidFix.trim().toUpperCase()==="FREE-S2Y"){
        localStorage.setItem(LS_GAME_ID, "FREE-S2");
        try{
          var _used=JSON.parse(localStorage.getItem(LS_GAME_USED)||"{}");
          if(_used["FREE-S2Y"]){ _used["FREE-S2"]=true; delete _used["FREE-S2Y"]; localStorage.setItem(LS_GAME_USED, JSON.stringify(_used)); }
        }catch(e2){}
        try{
          var _pl=JSON.parse(localStorage.getItem(LS_PLAN)||"null");
          if(_pl && _pl.gameId && _pl.gameId.toUpperCase()==="FREE-S2Y"){ _pl.gameId="FREE-S2"; localStorage.setItem(LS_PLAN, JSON.stringify(_pl)); }
        }catch(e3){}
        try{
          var _u=JSON.parse(localStorage.getItem(LS_USER)||"null");
          if(_u && _u.gameId && _u.gameId.toUpperCase()==="FREE-S2Y"){ _u.gameId="FREE-S2"; localStorage.setItem(LS_USER, JSON.stringify(_u)); }
        }catch(e4){}
      }
    }catch(e){}
    // prefill game id — refresh pe hamesha default FREE-S2
    try{
      if(gameIn) gameIn.value=uid();
    }catch(e){}

    // WIP popup helpers — Pay Now = Work in Progress
    function showWip(){
      var ov=document.getElementById("wipOverlay");
      if(ov){ ov.classList.remove("hidden"); }
    }
    function hideWip(){
      var ov=document.getElementById("wipOverlay");
      if(ov){ ov.classList.add("hidden"); }
    }
    // bind WIP close
    (function(){
      var ov=document.getElementById("wipOverlay");
      var ok=document.getElementById("wipOk");
      if(ok) ok.addEventListener("click", hideWip);
      if(ov) ov.addEventListener("click", function(e){ if(e.target===ov) hideWip(); });
      document.addEventListener("keydown", function(e){ if(e.key==="Escape") hideWip(); });
    })();

    // FUNDED FIRM — single card selector logic
    var selectedPlan="free";
    var fundedOpts=document.querySelectorAll(".funded-opt");
    function isPlanActive(cur){
      if(!cur) return false;
      if(cur.type==="free"){
        if(cur.until){
          try{
            // Exact time check — supports both old date-only (YYYY-MM-DD) and new ISO timestamp
            var exp = new Date(cur.until).getTime();
            // Old date-only stored as YYYY-MM-DD → treat as end of that day 23:59:59
            if(cur.until && cur.until.indexOf("T")===-1 && !isNaN(exp)) exp += (24*3600*1000 - 1000);
            return exp > Date.now();
          }catch(e){ return true; }
        } return true;
      }
      if(cur.type==="pro"){
        if(cur.until){
          try{ return new Date(cur.until).getTime() > Date.now(); }catch(e){ return true; }
        }
        return true;
      }
      return false;
    }
    function renderPlan(p){
      selectedPlan=p;
      fundedOpts.forEach(function(b){ b.classList.toggle("active", b.getAttribute("data-plan")===p); });
      if(!fundedBadge || !fundedName || !fundedPriceRow || !fundedFeats || !fundedCta) return;
      var curActive=loadPlan();
      var active=isPlanActive(curActive);
      if(p==="free"){
        fundedBadge.textContent="FREE \u2022 7 DAYS"; fundedBadge.className="funded-badge";
        fundedName.textContent="Free Trial";
        if(fundedDesc){ fundedDesc.innerHTML=""; fundedDesc.style.display="none"; }
        fundedPriceRow.innerHTML='<span class="price-now">\u20B90</span><span style="color:#6b6b80; margin:0 2px;">/</span><span class="price-old">\u20B9199</span><span class="price-off">100% OFF</span>';
        if(gameWrap) gameWrap.classList.remove("hidden");
        fundedFeats.innerHTML='<div class="feat"><span class="tick">\u2713</span> 7 days unlimited voice & chat</div><div class="feat"><span class="tick">\u2713</span> Live companion + history</div><div class="feat"><span class="tick">\u2713</span> 1 ID = 1 Free only (stored locally)</div>';
        if(active && curActive && curActive.type==="free"){
          fundedCta.textContent="\u2713 Free Plan Activated \u2014 Open App \u2192"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-free";
        } else {
          var gid=(gameIn?gameIn.value.trim().toUpperCase():"");
          var isFreeS2=gid==="FREE-S2";
          var freeUsed=isFreeUsed("FREE-S2");
          if(isFreeS2 && freeUsed){ fundedCta.textContent="FREE-S2 Already Used \u2014 One Time Only"; fundedCta.disabled=true; fundedCta.className="funded-cta cta-free"; }
          else if(!isFreeS2 && gid){ fundedCta.textContent="Code Changed \u2192 Auto 1 Month (\u20B999)"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-pro"; }
          else { fundedCta.textContent="Activate Free \u2014 7 Days"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-free"; }
        }
      } else if(p==="1m"){
        fundedBadge.textContent="\uD83D\uDD25 POPULAR \u2022 1 MONTH"; fundedBadge.className="funded-badge basic";
        fundedName.textContent="Basic Plan \u2014 1 Month";
        if(fundedDesc){ fundedDesc.style.display=""; fundedDesc.textContent="Everything unlimited \u2014 best voice quality, priority response, all border styles & themes."; }
        fundedPriceRow.innerHTML='<span class="price-now">\u20B999</span><span style="color:#6b6b80; margin:0 2px;">/</span><span class="price-old">\u20B9199</span><span class="price-off">50% OFF</span><span style="font-size:10px; color:#8a8aa3; margin-left:6px;">per month</span>';
        if(gameWrap) gameWrap.classList.add("hidden");
        fundedFeats.innerHTML='<div class="feat"><span class="tick">\u2713</span> Unlimited voice, chat & history</div><div class="feat"><span class="tick">\u2713</span> All 17 border designs + 12 themes</div><div class="feat"><span class="tick">\u2713</span> Early new features + support</div>';
        if(active && curActive && curActive.type==="pro" && (curActive.tenure==="1m" || curActive.price && curActive.price.indexOf("99")!==-1 && curActive.tenure!=="1y" && curActive.tenure!=="3m")){
          fundedCta.textContent="\u2713 Pro Plan Activated \u2014 Open App \u2192"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-free";
        } else { fundedCta.textContent="Pay Now \u2014 \u20B999 / month"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-pro"; }
      } else if(p==="3m"){
        fundedBadge.textContent="VALUE \u2022 3 MONTHS"; fundedBadge.className="funded-badge pro";
        fundedName.textContent="Pro Plan \u2014 3 Months";
        if(fundedDesc){ fundedDesc.style.display=""; fundedDesc.textContent="Quarterly value \u2014 3 months unlimited, best for regular users. All pro features."; }
        fundedPriceRow.innerHTML='<span class="price-now">\u20B9199</span><span style="color:#6b6b80; margin:0 2px;">/</span><span class="price-old">\u20B9299</span><span class="price-off">33% OFF</span><span style="font-size:10px; color:#8a8aa3; margin-left:6px;">for 3 months</span>';
        if(gameWrap) gameWrap.classList.add("hidden");
        fundedFeats.innerHTML='<div class="feat"><span class="tick">\u2713</span> 3 months unlimited voice, chat & history</div><div class="feat"><span class="tick">\u2713</span> All 17 border designs + 12 themes</div><div class="feat"><span class="tick">\u2713</span> Priority response + faster voice</div><div class="feat"><span class="tick">\u2713</span> Quarterly early features + support</div>';
        if(active && curActive && curActive.type==="pro" && curActive.tenure==="3m"){
          fundedCta.textContent="\u2713 Pro Plan Activated \u2014 Open App \u2192"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-free";
        } else { fundedCta.textContent="Pay Now \u2014 \u20B9199 / 3 months"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-pro"; }
      } else if(p==="1y"){
        fundedBadge.textContent="\uD83D\uDC51 BEST \u2022 1 YEAR"; fundedBadge.className="funded-badge premium";
        fundedName.textContent="Premium Plan \u2014 1 Year";
        if(fundedDesc){ fundedDesc.style.display=""; fundedDesc.textContent="Best value \u2014 12 months unlimited, save 80% vs monthly. Yearly exclusive perks."; }
        fundedPriceRow.innerHTML='<span class="price-now">\u20B9999</span><span style="color:#6b6b80; margin:0 2px;">/</span><span class="price-old">\u20B91200</span><span class="price-off">17% OFF</span><span style="font-size:10px; color:#8a8aa3; margin-left:6px;">per year</span>';
        if(gameWrap) gameWrap.classList.add("hidden");
        fundedFeats.innerHTML='<div class="feat"><span class="tick">\u2713</span> 12 months unlimited voice, chat & lifetime history</div><div class="feat"><span class="tick">\u2713</span> All 17 border designs + 12 themes + future drops free</div><div class="feat"><span class="tick">\u2713</span> Priority response + ultra-fast voice</div><div class="feat"><span class="tick">\u2713</span> Exclusive yearly badge + Beta early access</div><div class="feat"><span class="tick">\u2713</span> Dedicated priority support + feature requests</div>';
        if(active && curActive && curActive.type==="pro" && curActive.tenure==="1y"){
          fundedCta.textContent="\u2713 Premium Plan Activated \u2014 Open App \u2192"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-free";
        } else { fundedCta.textContent="Pay Now \u2014 \u20B9999 / year"; fundedCta.disabled=false; fundedCta.className="funded-cta cta-pro"; }
      }
      // hint — use fresh plan
      if(freeHint){
        var gid2=(gameIn?gameIn.value.trim().toUpperCase():"");
        var isFreeS2_2=gid2==="FREE-S2";
        var freeUsed2=isFreeUsed("FREE-S2");
        var curHint=loadPlan();
        if(curHint && curHint.type==="free" && isPlanActive(curHint)){ try{ var d=new Date(curHint.until); var fmt=d.toLocaleString("en-IN",{day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit"}); freeHint.textContent="Active: Free till "+fmt; }catch(e){ freeHint.textContent="Active: Free till "+(curHint.until||"7 days"); } }
        else if(p==="free" && isFreeS2_2 && freeUsed2) freeHint.textContent="FREE-S2 Already Used \u2014 Please Choose Pro";
        else if(p==="free" && !isFreeS2_2 && gid2) freeHint.textContent="Different from FREE-S2 \u2192 Auto 1 Month Basic";
        else if(p==="free") freeHint.textContent="Code FREE-S2 = 7D Free \u2022 Any Change \u2192 1 Month Pro";
        else freeHint.textContent="Pro Payment is Work in Progress \u2014 Only FREE-S2 Can Load MUSKU";
      }
      // re-trigger animation
      if(fundedPriceRow){ fundedPriceRow.style.animation="none"; fundedPriceRow.offsetHeight; fundedPriceRow.style.animation=""; }
    }
    fundedOpts.forEach(function(btn){
      btn.addEventListener("click", function(){ renderPlan(btn.getAttribute("data-plan")||"free"); });
    });
    if(gameIn) gameIn.addEventListener("input", function(){ if(selectedPlan==="free") renderPlan("free"); });
    renderPlan(selectedPlan);
    // Sync Firebase 1 Gmail = 1 Free + active plan cross-device (exact time)
    try{ checkFreeClaimedFirebase().then(function(claimed){ if(claimed) renderPlan(selectedPlan); }); }catch(e){}
    try{ syncFreePlanFromFirebase(); }catch(e){}
    try{ syncActivationFromFirebase(); }catch(e){}
    // Show existing local activation key if any
    try{
      var _uidK=getCurrentUid();
      var _kLocal=null;
      if(_uidK) _kLocal=localStorage.getItem(LS_ACT_KEY+"_"+_uidK);
      if(!_kLocal) _kLocal=localStorage.getItem(LS_ACT_KEY);
      // if already has active plan, reflect in key hint
      var _curPlan=loadPlan();
      if(_curPlan && isPlanActive(_curPlan) && _kLocal){
        var _kh=document.getElementById("keyHint");
        if(_kh){ _kh.textContent="Active key linked — use on other devices"; _kh.className="key-hint ok"; }
      }
    }catch(e){}
    // === I have activation key — wiring ===
    (function(){
      var kin=document.getElementById("keyInput");
      var kbtn=document.getElementById("keyActivateBtn");
      var kh=document.getElementById("keyHint");
      function setHint(msg, cls){ if(!kh) return; kh.textContent=msg; kh.className="key-hint"+(cls?" "+cls:""); }
      if(!kbtn || !kin) return;
      kbtn.addEventListener("click", function(){
        var raw=(kin.value||"").trim().toUpperCase();
        if(!raw){ setHint("Enter your activation key", "err"); kin.focus(); return; }
        if(raw.length < 10){ setHint("Invalid key format", "err"); return; }
        kbtn.disabled=true; kbtn.textContent="Verifying…"; setHint("Verifying key…", "");
        // 1) try remote lookup first (Pro: hash opaque + rate-limit + HMAC verify)
        lookupActivationKeyRemote(raw).then(function(remote){
          if(remote && remote.__rateLimited){
            setHint("Too many attempts — 5 tries / 5 min, please wait", "err");
            kbtn.disabled=false; kbtn.textContent="Activate";
            return;
          }
          if(remote){
            activateWithKeyData(raw, remote);
            saveUser(Object.assign({}, u, { gameId:remote.gameId||"FREE-S2" }));
            confettiBurst();
            setHint("Key valid — "+(remote.planType==="free"?"Free 7D":"Pro "+(remote.tenure||""))+" unlocked ✓", "ok");
            renderPlan(selectedPlan);
            kbtn.disabled=false; kbtn.textContent="Activate";
            setTimeout(function(){ goApp(); }, 900);
            return;
          }
          // 2) fallback: local meta check (offline / same device key)
          try{
            var meta=null;
            var uidChk=getCurrentUid();
            if(uidChk) try{ meta=JSON.parse(localStorage.getItem(LS_ACT_META+"_"+uidChk)||"null"); }catch(e){}
            if(!meta) try{ meta=JSON.parse(localStorage.getItem(LS_ACT_META)||"null"); }catch(e){}
            if(meta && meta.key && meta.key.toUpperCase()===raw){
              var exp2=new Date(meta.until).getTime();
              if(!isNaN(exp2) && exp2 > Date.now()){
                activateWithKeyData(raw, meta);
                saveUser(Object.assign({}, u, { gameId:"FREE-S2" }));
                confettiBurst();
                setHint("Key valid (local) — unlocked ✓", "ok");
                renderPlan(selectedPlan);
                kbtn.disabled=false; kbtn.textContent="Activate";
                setTimeout(function(){ goApp(); }, 900);
                return;
              } else { setHint("Key expired — please get a new key", "err"); }
            } else { setHint("Invalid or expired key", "err"); }
          }catch(e){ setHint("Invalid key", "err"); }
          kbtn.disabled=false; kbtn.textContent="Activate";
        }).catch(function(){
          setHint("Verification failed — try again", "err");
          kbtn.disabled=false; kbtn.textContent="Activate";
        });
      });
      if(kin) kin.addEventListener("keydown", function(e){ if(e.key==="Enter"){ e.preventDefault(); kbtn.click(); }});
      if(kin) kin.addEventListener("input", function(){ kin.value=kin.value.toUpperCase(); });
    })();

    // Single CTA handler — funded firm style (active plan → Open App) + 1 Gmail = 1 Free
    var fundedCtaEl=document.getElementById("fundedCta");
    if(fundedCtaEl) fundedCtaEl.addEventListener("click", function(){
      // If CTA already shows Activated → instant Open App
      if(fundedCtaEl.textContent.indexOf("Activated")!==-1){ goApp(); return; }
      var curCheck=loadPlan();
      if(isPlanActive(curCheck)){
        if((curCheck.type==="free" && selectedPlan==="free") || (curCheck.type==="pro" && (curCheck.tenure===selectedPlan))){ goApp(); return; }
        if(curCheck.type==="pro" && fundedCtaEl.textContent.indexOf("Activated")!==-1){ goApp(); return; }
      }
      if(selectedPlan==="1m" || selectedPlan==="3m" || selectedPlan==="1y"){
        showWip();
        return;
      }
      var gid=(gameIn?gameIn.value.trim():"").toUpperCase();
      if(!gid){ toast("Enter Code \u2014 FREE-S2"); if(gameIn) gameIn.focus(); return; }
      if(gid !== "FREE-S2"){
        try{ localStorage.setItem(LS_GAME_ID, gid); }catch(e){}
        var sincePro=new Date().toISOString();
        var untilPro=new Date(Date.now()+30*24*3600*1000).toISOString();
        savePlan({ type:"pro", tenure:"1m", price:"\u20B999 / month", orig:"\u20B9499", since:sincePro, until:untilPro, gameId:gid });
        saveUser(Object.assign({}, u, { gameId:gid }));
        try{ createAndStoreActivationKey("pro","1m"); var khp=document.getElementById("keyHint"); if(khp){ khp.textContent="Pro plan activated ✓"; khp.className="key-hint ok"; } }catch(e){}
        confettiBurst();
        renderPlan("free");
        showWip();
        return;
      }
      // 1 Gmail = 1 Free — check local + Firebase (async)
      if(isFreeUsed("FREE-S2")){
        toast("FREE-S2 Already Used \u2014 One Time Only (1 Gmail = 1 Free)");
        return;
      }
      // Async Firebase cross-device check before claim
      checkFreeClaimedFirebase().then(function(fbClaimed){
        if(fbClaimed || isFreeUsed("FREE-S2")){
          try{ var uidChk=getCurrentUid(); if(uidChk) try{ localStorage.setItem("musku_free_claimed_"+uidChk,"1"); }catch(e){} }catch(e){}
          toast("FREE-S2 Already Used \u2014 One Time Only (1 Gmail = 1 Free)");
          renderPlan("free");
          return;
        }
        var until=new Date(Date.now()+7*24*3600*1000).toISOString();
        var since=new Date().toISOString();
        markFreeUsed("FREE-S2");
        savePlan({ type:"free", gameId:"FREE-S2", since:since, until:until });
        saveUser(Object.assign({}, u, { gameId:"FREE-S2" }));
        // Generate secure activation key bound to days (Pro pattern)
        try{
          var res=createAndStoreActivationKey("free","free");
          // also ensure until matches generated (7d) — keep original until
          try{ var kh2=document.getElementById("keyHint"); if(kh2){ kh2.textContent="Free plan activated ✓ — saved to your Gmail"; kh2.className="key-hint ok"; } }catch(e){}
        }catch(e){}
        confettiBurst();
        setTimeout(function(){ goApp(); }, 700);
      }).catch(function(){
        // Fallback if Firebase check fails — proceed with local check only
        if(isFreeUsed("FREE-S2")){ toast("FREE-S2 Already Used \u2014 One Time Only"); return; }
        var until2=new Date(Date.now()+7*24*3600*1000).toISOString();
        var since2=new Date().toISOString();
        markFreeUsed("FREE-S2");
        savePlan({ type:"free", gameId:"FREE-S2", since:since2, until:until2 });
        saveUser(Object.assign({}, u, { gameId:"FREE-S2" }));
        try{
          var res2=createAndStoreActivationKey("free","free");
        }catch(e){}
        confettiBurst();
        setTimeout(function(){ goApp(); }, 700);
      });
    });

    // legacy compat: if old buttons exist (hidden), keep them working
    if(freeBtn) freeBtn.addEventListener("click", function(){ var c=document.getElementById("fundedCta"); if(c) c.click(); });
    if(proBtn) proBtn.addEventListener("click", function(){ showWip(); });

    // Back — instant redirect to Sign in (left side)
    var backBtn=document.getElementById("backBtn");
    if(backBtn) backBtn.addEventListener("click", function(){ location.replace("signup.html"); });
    // Open App — instant redirect if ANY active plan (free/pro) else inline msg
    var openAppBtn=document.getElementById("openAppBtn");
    if(openAppBtn) openAppBtn.addEventListener("click", function(){
      var curPlan=null;
      try{ curPlan=loadPlan(); }catch(e){}
      // fallback to generic LS_PLAN for legacy
      if(!curPlan) try{ curPlan=JSON.parse(localStorage.getItem(LS_PLAN)||"null"); }catch(e){}
      var isActive=false;
      if(curPlan){
        var untilOk=true;
        if(curPlan.until){
          try{ var now=new Date(); var until=new Date(curPlan.until); untilOk = until >= now; }catch(e){ untilOk=true; }
        }
        if(curPlan.type==="free" || curPlan.type==="pro"){
          if(untilOk) isActive=true;
        } else if(curPlan.planType==="free" || curPlan.planType==="pro"){
          if(untilOk) isActive=true;
        }
      }
      if(isActive){
        var im=document.getElementById("inlineMsg"); if(im){ im.classList.remove("show"); im.classList.add("hidden"); }
        location.replace("index.html");
      } else {
        var inlineMsg=document.getElementById("inlineMsg");
        if(inlineMsg){
          inlineMsg.textContent="No active plan found. Please activate a plan to continue — choose FREE-S2 (7 Days Free) or select a Pro plan. Need help? Contact Musku Support.";
          inlineMsg.classList.remove("hidden");
          void inlineMsg.offsetHeight;
          inlineMsg.classList.add("show");
          setTimeout(function(){ inlineMsg.classList.remove("show"); setTimeout(function(){ inlineMsg.classList.add("hidden"); }, 320); }, 3200);
        } else {
          toast("No active plan found. Please activate a plan to continue — choose FREE-S2 (7 Days Free) or select a Pro plan. Need help? Contact Musku Support.", 3200);
        }
      }
    });
    // logout — legacy (other pages) code changed ho to Sign out pe 1 Month Pro me convert (instant)
    var lo1=document.getElementById("logoutFree"), lo2=document.getElementById("logoutPro");
    var singleOut=logoutBtn||lo1||lo2;
    function doLogout(){
      try{
        var gid=(gameIn?gameIn.value.trim().toUpperCase():"");
        if(gid && gid !== "FREE-S2"){
          try{ localStorage.setItem(LS_GAME_ID, gid); }catch(e){}
          savePlan({ type:"pro", tenure:"1m", price:"\u20B999 / month", orig:"\u20B9499", since:new Date().toISOString(), gameId:gid });
        }
      }catch(e){}
      try{ localStorage.removeItem(LS_USER);}catch(e){} if(fbAuth) try{fbAuth.signOut();}catch(e){}
      goSignup();
    }
    if(singleOut) singleOut.addEventListener("click", doLogout);
    if(lo1 && lo1!==singleOut) lo1.addEventListener("click", doLogout);
    if(lo2 && lo2!==singleOut) lo2.addEventListener("click", doLogout);
    // Ensure all interactive options are instant — remove any passive delay, direct handlers already instant (funded-opt, fundedCta, back, openApp, logout)
  }

  window.MuskuAuth={ initSignup:initSignup, initActivate:initActivate, loadUser:loadUser, loadPlan:loadPlan, goApp:goApp, goSignup:goSignup, toast:toast };
  // auto init for signup page
  document.addEventListener("DOMContentLoaded", function(){
    if(document.getElementById("googleBtn")) initSignup();
  });
})();
