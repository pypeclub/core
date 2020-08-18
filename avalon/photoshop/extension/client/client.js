    function restart_extension() {
      log.warn("restarting!");
      try {
          ////////////////////////////////////////////////////////////////////////////////////////////////////
          // if we're restarting then we should remove all the eventListeners so we don't get double events //
          // Try get the point over                                                                         //
          // CRITICAL MAKE SURE TO CLOSE NULLIFY ETC. ANY LOOSE WATCHERS, EVENTLISTENERS, GLOBALS ETC.      //
          // CRITICAL MAKE SURE TO CLOSE NULLIFY ETC. ANY LOOSE WATCHERS, EVENTLISTENERS, GLOBALS ETC.      //
          // CRITICAL MAKE SURE TO CLOSE NULLIFY ETC. ANY LOOSE WATCHERS, EVENTLISTENERS, GLOBALS ETC.      //
          // CRITICAL MAKE SURE TO CLOSE NULLIFY ETC. ANY LOOSE WATCHERS, EVENTLISTENERS, GLOBALS ETC.      //
          // for example watcher.close();                                                                   //
          // Then reset the UI to load it's page (if it hasn't change page)                                 //
          ////////////////////////////////////////////////////////////////////////////////////////////////////
          process.removeAllListeners();
          window.location.href = "./index.html";
      } catch (e) {
          window.location.href = "./index.html";
      }
    }
    
    function myCallBack(){
        log.warn("Triggered index.jsx");
    }
    
    var logReturn = function(result){ log.warn('Result: ' + result);};
    
    var csInterface = new CSInterface();
    jsx.evalFile('./host/index.jsx', myCallBack);
    
    log.warn("script start");

    WSRPC.DEBUG = true;
    WSRPC.TRACE = true;

    var url = (window.location.protocol==="https):"?"wss://":"ws://") +
              window.location.host + '/ws/';
    url = 'ws://localhost:8099/ws/';
    RPC = new WSRPC(url, 5000);

    RPC.connect();

    log.warn("connected");
    
    function EscapeStringForJSX(str)
    {
    // Replaces:
    //  \ with \\
    //  ' with \'
    //  " with \"
    // See: https://stackoverflow.com/a/3967927/5285364
        return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
    }

    function runEvalScript(script) {
        return new Promise(function(resolve, reject){
            csInterface.evalScript(script, resolve);
        });
    }
    
    RPC.addRoute('Photoshop.read', function (data) {
            log.warn('Server called client route "read":', data);
            return runEvalScript("getHeadline()")
                .then(function(result){
                    log.warn("getHeadline: " + result);
                    return result;
                });
    });

    RPC.addRoute('Photoshop.get_layers', function (data) {
            log.warn('Server called client route "get_layers":', data);
            return runEvalScript("getLayers()")
                .then(function(result){
                    log.warn("getLayers: " + result);
                    return result;
                });
    });
    
    RPC.addRoute('Photoshop.saveAs', function (data) {
            log.warn('Server called client route "saveAsJPEG":', data);
            var escapedPath = EscapeStringForJSX(data.image_path);
            return runEvalScript("saveAs('" + escapedPath + "', " +
                                         "'" + data.ext + "', " + 
                                         data.as_copy + ")")
                .then(function(result){
                    log.warn("save: " + result);
                    return result;
                });
    });
    
    RPC.addRoute('Photoshop.set_visible', function (data) {
            log.warn('Server called client route "saveAsJPEG":', data);
            return runEvalScript("setVisible(" + data.layer_id + ", " 
                                 + data.visibility + ")")
                .then(function(result){
                    log.warn("setVisible: " + result);
                    return result;
                });
    });
    
    RPC.addRoute('Photoshop.get_active_document_name', function (data) {
            log.warn('Server called client route "get_active_document_name":', data);
            return runEvalScript("getActiveDocumentName()")
                .then(function(result){
                    log.warn("save: " + result);
                    return result;
                });
    });
    
    
    RPC.call('Photoshop.ping').then(function (data) {
        log.warn('Result for calling server route "ping": ', data);           
    }, function (error) {
        log.warn(error);
    });
    
    runEvalScript("setVisible(6, true)")
                .then(function(result){
                    log.warn("setVisible: " + result);
                    return result;
                });

    log.warn("end script");
