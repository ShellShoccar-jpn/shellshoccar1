// ###################################################################
// # 共通関数
// ###################################################################

// ===== 本システムのホームディレクトリの絶対URLを得る ===============
// [入力]
// ・なし
// [出力]
// ・本システムのホームディレクトリーの絶対URL文字列
//   - 文字列の最後には "/" が付いている。従ってこのURLを元に、別のファ
//     イルやディレクトリーの絶対URLを作る時、付け足す文字列の先頭に "/"
//     は不要である。
//   - 失敗時はnull
// [備考]
// ・JavaScriptにとって、自分のプログラムファイルが置かれている絶対URL
//   を自力で知るのは難しい。理由は、呼び出し側HTMLのカレントURL(絶対
//   URL)が与えられるからだ。
// ・そこで呼び出し側HTMLの中にある、呼び出し元の<script src="...">を探
//   し出し、そのURL情報を使ってカレントURL(絶対URL)に位置補正を行い、
//   自身の絶対URLを検出する。
function get_homedir() {

  // --- 自分自身に関する情報の設定(自分の位置を検出するために必要) --
  var sThis_filename    = 'JS/CLIENTBASE.JS'; // このファイルの名前(*1)
  var sPath_to_the_home = '..';               // ↑のホームdirへの相対パス
     // (*1) 同名ファイルが他に存在するなどして、ファイル名だけでは一意
     //      に絞り込めない場合、「<script src="~">で必ず含めると保証さ
     //      れている」のであれば、親ディレクトリーなどを含めてもよい。
     //      例えば、1つのサイトの中の
     //        あるHTMLでは<script src="myjs/script.js">
     //        またあるHTMLでは<script src="../myjs/script.js">
     //      というように、全てのHTMLで "myjs/script.js" 部分を必ず指定
     //      しているなら、他の "otherjs/script.js" と間違わないように、
     //        sThis_filename = 'myjs/script.js' としてもよい。
     //      ただしこの時 sLocation_from_home は、"myjs" の場所から見た
     //      ホームディレクトリーへの相対パスを意味するので注意。

  // --- その他変数定義 ----------------------------------------------
  var i, s, le; // 汎用変数
  var sUrl = null; // 戻り文字列格納用

  // --- 自JavaScriptを読んでいるタグを探し、homedir(相対の場合あり)を生成
  le = document.getElementsByTagName('script');
  for (i=0; i<le.length; i++) {
    s = le[i].getAttribute('src');
    if (s.length < sThis_filename.length) {continue;}
    if (s.substr(s.length-sThis_filename.length) !== sThis_filename) {continue;}
    s = s.substr(0,s.length-sThis_filename.length);
    if ((s.length>0) && s.match(/[^\/]$/)) {continue;}
    sUrl = s + sPath_to_the_home;
    sUrl = (sUrl.match(/\/$/)) ? sUrl : sUrl+'/';
    break;
  }
  if (i >= le.length) {
    return null;             // タグが見つからなかったらnullを返して終了
  }

  // --- 絶対パス化(.や..は含む) -------------------------------------
  if (     sUrl.match(/^http/i)) {
    // httpから始まるURLになっていたらそのままでよい
  }
  else if (sUrl.match(/^\//)   ) {
    // httpから始まらないが絶対パスになっている場合はhttp～ドメイン名までを先頭に付ける
    if (! location.href.match(/^(https?:\/\/[a-z0-9.-]+)/i)) {return null;}
    sUrl = RegExp.$1 + sUrl;
  }
  else                           {
    // 相対パスになっている場合は呼び出し元URLのディレクトリまでの部分を先頭に付ける
    sUrl = location.href.replace(/\/[^\/]*$/, '/') + sUrl;
  }

  // --- カレントディレクトリ表記(.)を除去 ---------------------------
  while (sUrl.match(/\/\.\//)) {
    sUrl = sUrl.replace(/\/\.\//g, '/');
  }

  // --- 親ディレクトリ表記(..)を除去 --------------------------------
  sUrl.match(/^(https?:\/\/[A-Za-z0-9.-]+)(\/.*)$/);
  s    = RegExp.$1;
  sUrl = RegExp.$2;
  while (sUrl.match(/\/\.\.\//)) {
    while (sUrl.match(/^\/\.\.\//)) {
      sUrl = sUrl.replace(/^\/\.\.\//, '/');
    }
    sUrl = sUrl.replace(/^\/\.\.$/, '/');
    while (sUrl.match(/\/[^\/]+\/\.\.\//)) {
      sUrl = sUrl.replace(/\/[^\/]+\/\.\.\//, '/');
    }
  }
  sUrl = s + sUrl;

  // --- 正常終了 ----------------------------------------------------
  return sUrl;
}


// ===== Ajaxのお約束オブジェクト作成 ================================
function createXMLHttpRequest(){
  if(window.XMLHttpRequest){return new XMLHttpRequest()}
  if(window.ActiveXObject){
    try{return new ActiveXObject("Msxml2.XMLHTTP.6.0")}catch(e){}
    try{return new ActiveXObject("Msxml2.XMLHTTP.3.0")}catch(e){}
    try{return new ActiveXObject("Microsoft.XMLHTTP")}catch(e){}
  }
  return false;
}


// ###################################################################
// # カゴ入れボタン系
// ###################################################################

// ===== カゴに入れるボタン押下時の処理 ==============================
// [入力]
//   eAdd1: 押下されたadd1ボタンのエレメント(*備考)
// [出力]
//   ・サーバーで管理しているセッションの中に商品IDと数量が追加される
//   ・成功時は画面更新関数が呼び出される
// [備考]
//   ・押下されたボタンは一つのformに所属していること
//   ・そのformは次の仕様を満たしていること
//     - name="pid" value="<商品ID>" な<input>タグを持っていること
//     - name="qty"で、数量0からn個(任意)までのoptionを保持する<select>
//       タグを持っていること
function add_one_to_cart(eAdd1) {
  var i, n, s;      // 汎用変数
  var ePid, eQty;   // pid,qty用のエレメントオブジェクト格納用
  var sPid, iQty;   // pid,qtyの値格納用
  var xhr;          // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/ADDTOCART.AJAX.CGI';  // AjaxのURL定義

  // --- 1)商品ID、数量エレメントを見つける --------------------------
  for (i=0; i<eAdd1.form.length; i++) {
    if      (eAdd1.form[i].name === 'pid') {
      ePid = eAdd1.form[i];
    }
    else if (eAdd1.form[i].name === 'qty') {
      eQty = eAdd1.form[i];
    }
    if ((ePid !== undefined) && (eQty !== undefined)) {
      break;
    }
  }
  if ((ePid == undefined) || (eQty == undefined)) {
    alert('pty,qtyフォームが見つからない!');
    return;
  }

  // --- 2)商品IDを取得 ----------------------------------------------
  sPid = ePid.value;

  // --- 3)数量を取得し、最大値未満なら+1する ------------------------
  if (       eQty.tagName === 'SELECT') {
    n = 0;
    for (i=0; i<eQty.options.length; i++) {
      n = (n>=(eQty.options.item(i).value * 1)) ? n * 1 : eQty.options.item(i).value * 1;
    }
    iQty = eQty.options.item(eQty.selectedIndex).value * 1;
    if (iQty >= n) {
      //既に最大値に達しているならalert終了
      alert('一度に購入できる数の上限、または残り在庫数の上限に達しため、この商品はこれ以上追加できません。');
      return;
    }
    iQty++;
    for (i=0; i<eQty.options.length; i++) {
      if (eQty.options.item(i).value == iQty) {
        eQty.selectedIndex = i;
        break;
      }
    }
  } else if (eQty.tagName === 'INPUT' ) {
    n = 0;
    for (i=0; i<eAdd1.form.length; i++) {
      if (eAdd1.form[i].name === 'avail_qtys') {n = eAdd1.form[i].value * 1;}
    }
    iQty = (eQty.value.match(/^[0-9]+$/)) ? eQty.value*1 : 0;
    if (iQty >= n) {
      //既に最大値に達しているならalert終了
      alert('一度に購入できる数の上限、または残り在庫数の上限に達しため、この商品はこれ以上追加できません。');
      return;
    }
    iQty++;
    //eQty.value = iQty;
  }

  // --- 4)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = 'pid='+sPid+'&qty='+iQty.toString();
    s += '&dummy='+parseInt((new Date)/1);               //キャッシュ対策

    xhr.open('POST', sUrl_ajax, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.onreadystatechange = function(){add_del_cart_callback(xhr, iQty, false)};
    xhr.withCredentials = true;         // ↑コールバック関数はadd&del共用
    xhr.send(s);
  }

  // --- 5)処理が完了するまでボタンを連打できなくする ----------------
  cart_controls_concealer(true);
    //loading_cover_make();
    //i = new Date().getTime()/1000;
    //loading_cover_fadein(0.8, i, i+0.5, 0.05);
}
function add_del_cart_callback(xhr, iQty, bNotify) {

  var iRet; // サーバーからの戻り値
  var e;    // 汎用変数

  // --- 6)アクセス成功で呼び出されたのでないなら即終了 --------------
  if (xhr.readyState != 4) {return;}
  if (xhr.status == 0) {return;} // ステータスが0の場合はクライアントによる中断の可能性があるので無視
  if (xhr.status != 200) {
    alert('アクセスエラー(' + xhr.status + ')');
    return;
  }

  // --- 7)失敗ステータスで帰ってきた場合はメッセージ表示後、終了 ----
  iRet = xhr.responseText * 1; // 成功していたらステータスコードを取得
  if (iRet != 0) {
    alert('カゴの内容を変更するのに失敗しました!');
    return;
  }

  // --- 8)成功メッセージを表示 --------------------------------------
  cart_controls_concealer(false);
    //loading_cover_remove();
  if      ((bNotify === true) && (iQty != 0)) {
    alert('商品をカゴに追加しました');
  }
  else if ((bNotify === true) && (iQty == 0)) {
    alert('商品をカゴから削除しました');
  }

  // --- 9)商品関連フォームの状態を更新 ------------------------------
  e = document.getElementById('receipt_tbl');
  if (e) {
    // 会計テーブルがあれば会計テーブル更新関数を呼ぶ
    get_receipt_html_parts(e,true);
  } else {
    // 会計テーブルがなければフォームコントロール更新関数だけ呼ぶ
    update_product_ctrl_area();
  }

  // --- 99)正常終了 -------------------------------------------------
  return;
}


// ===== 数量<select>タグを変更した時の処理 ==========================
// [入力]
//   eSel: 変更された<select name="qty">のエレメント(*備考)
// [出力]
//   ・サーバーで管理しているセッションの中に商品IDと数量が追加される
//   ・成功時は画面更新関数が呼び出される
// [備考]
//   ・押下されたボタンは一つのformに所属していること
//   ・そのformは次の仕様を満たしていること
//     - name="pid" value="<商品ID>" な<input>タグを持っていること
//     - name="qty"で、数量0からn個(任意)までのoptionを保持する<select>
//       タグを持っていること
function change_qty(eSel) {
  var i, n, s;      // 汎用変数
  var ePid, eQty;   // pid,qty用のエレメントオブジェクト格納用
  var sPid, iQty;   // pid,qtyの値格納用
  var xhr;          // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/ADDTOCART.AJAX.CGI';  // AjaxのURL定義

  // --- 1)商品ID、数量エレメントを見つける --------------------------
  for (i=0; i<eSel.form.length; i++) {
    if (eSel.form[i].name === 'pid') {
      ePid = eSel.form[i];
      break;
    }
  }
  eQty = eSel;
  if ((ePid == undefined) || (eQty == undefined)) {
    alert('pty,qtyフォームが見つからない!');
    return;
  }

  // --- 2)商品IDを取得 ----------------------------------------------
  sPid = ePid.value;

  // --- 3)数量を取得 ------------------------------------------------
  iQty = eQty.options.item(eQty.selectedIndex).value * 1;

  // --- 4)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = 'pid='+sPid+'&qty='+iQty.toString();
    s += '&dummy='+parseInt((new Date)/1);               //キャッシュ対策

    xhr.open('POST', sUrl_ajax, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.onreadystatechange = function(){add_del_cart_callback(xhr, iQty, true)};
    xhr.withCredentials = true;         // ↑コールバック関数はadd&del共用
    xhr.send(s);
  }

  // --- 5)処理が完了するまでボタンを連打できなくする ----------------
  cart_controls_concealer(true);
    //loading_cover_make();
    //i = new Date().getTime()/1000;
    //loading_cover_fadein(0.8, i, i+0.5, 0.05);
}


// ===== カゴから削除するボタン押下時の処理 ==========================
// [入力]
//   eDel: 押下されたボタンのエレメント(*備考)
// [出力]
//   ・数量選択<select>タグの値が0になる
//   ・サーバーで管理しているセッションの中から商品情報が削除される
//   ・成功時は画面更新関数が呼び出される
// [備考]
//   ・押下されたボタンは一つのformに所属していること
//   ・そのformは次の仕様を満たしていること
//     - name="pid" value="<商品ID>" な<input>タグを持っていること
//     - name="qty"で、数量0からn個(任意)までのoptionを保持する<select>
//       タグを持っていること
function del_from_cart(eDel) {
  var i, s;         // 汎用変数
  var ePid, eQty;   // pid,qty用のエレメントオブジェクト格納用
  var sPid, iQty;   // pid,qtyの値格納用
  var xhr;          // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/ADDTOCART.AJAX.CGI';  // AjaxのURL定義

  // --- 1)商品ID、数量エレメントを見つける --------------------------
  for (i=0; i<eDel.form.length; i++) {
    if      (eDel.form[i].name === 'pid') {
      ePid = eDel.form[i];
    }
    else if (eDel.form[i].name === 'qty') {
      eQty = eDel.form[i];
    }
    if ((ePid !== undefined) && (eQty !== undefined)) {
      break;
    }
  }
  if ((ePid == undefined) || (eQty == undefined)) {
    alert('pty,qtyフォームが見つからない!');
    return;
  }

  // --- 2)商品IDを取得 ----------------------------------------------
  sPid = ePid.value;

  // --- 3)数量<select>の値を0に変更し、数量も0に設定する ------------
  if (       eQty.tagName === 'SELECT') {
    if (eQty.options.item(eQty.selectedIndex).value == 0) {
      alert('この商品はカゴに入っていません');
      return;
    }
    for (i=0; i<eQty.options.length; i++) {
      if ((eQty.options.item(i).value * 1) == 0) {
        eQty.selectedIndex = i;
        break;
      }
    }
    if (i >= eQty.options.length) {
      alert('数量0の選択肢がない!');
      return;
    }
  } else if (eQty.tagName === 'INPUT' ) {
    if (eQty.value == 0) {
      alert('この商品はカゴに入っていません');
      return;
    }
    eQty.value = 0;
  }
  iQty = 0;

  // --- 4)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = 'pid='+sPid+'&qty='+iQty.toString();
    s += '&dummy='+parseInt((new Date)/1);               //キャッシュ対策

    xhr.open('POST', sUrl_ajax, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.onreadystatechange = function(){add_del_cart_callback(xhr, iQty, true)};
    xhr.withCredentials = true;         // ↑コールバック関数はadd&del共用
    xhr.send(s);
  }

  // --- 5)処理が完了するまでボタンを連打できなくする ----------------
  cart_controls_concealer(true);
    //loading_cover_make();
    //i = new Date().getTime()/1000;
    //loading_cover_fadein(0.8, i, i+0.5, 0.05);
}


// ###################################################################
// # 画面更新系
// ###################################################################

// ===== 商品ページ全体を更新 ========================================
// [入力]
//   なし
// [出力]
//   ・商品ページについて再描画すべき箇所を全部更新する
//     - 会員サインイン状態
//     - 商品関連フォームの内容
// [備考]
//   -
function update_whole_product_page() {
  //update_signedin_form();
  update_cookie_when_goback_from_cashier();
  update_product_ctrl_area();
}

// ===== 商品ページを更新 ============================================
// [入力]
//   なし
// [出力]
//   ・商品関連フォームの内容を更新する
// [備考]
//   -
function update_product_ctrl_area() {
  update_product_qtys();
  if (document.getElementById('goto_cashier')) {
    update_goto_cashier_button();
  }
}

// ===== 現在在庫数等を画面に反映 ====================================
// [入力]
//   なし
// [出力]
//   ・商品フォーム内の数量等を更新
// [備考]
//   -
function update_product_qtys() {
  var i,j,s,l,le;       // 汎用変数
  var oProd_form;       // ページ内商品<form>情報格納オブジェクト({商品ID:formエレメント, ...})
  var sPids             // ページ内商品ID一覧(カンマ区切り)
  var xhr;              // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/SHOWQTYS.AJAX.CGI';  // AjaxのURL定義

  // --- 1)更新が必要なフォームの一覧を集める ------------------------
  le = document.getElementsByTagName('form');
  oProd_form = new Object();
  for (i=0; i<le.length; i++) {
    if (! le[i].className.match(/\btakingform\b/)) {continue;}
    for (j=0; j<le[i].elements.length; j++) {
      if (le[i].elements[j].name  !== 'pid') {continue;}
      if (le[i].elements[j].value === '-'  ) {continue;}
      l = oProd_form[le[i].elements[j].value];
      if (l == undefined) { l = new Array(); }
      l.push(le[i]);
      oProd_form[le[i].elements[j].value] = l;
      break;
    }
  }
  // 対象フォームが1つもなければ何もせず終了
  if (Object.keys(oProd_form).length === 0) {return;}

  // --- 2)ページ内にある商品一覧(カンマ区切り)文字列を生成する ------
  sPids = Object.keys(oProd_form).join(',');

  // --- 3)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = 'pids='+sPids;
    s += '&dummy='+parseInt((new Date)/1);               //キャッシュ対策

    xhr.open('POST', sUrl_ajax, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.onreadystatechange
      = function(){update_product_qtys_callback(xhr, oProd_form)};
    xhr.withCredentials = true;
    xhr.send(s);
  }
}
function update_product_qtys_callback(xhr, oProd_form) {
  var n,i,j,k,e,e1,s,le,ls,iLP; // 汎用変数
  var oQty;                     // サーバーからJSONで渡ってきた数量情報JSON格納用

  // --- 4)アクセス成功で呼び出されたのでないなら即終了 --------------
  if (xhr.readyState != 4) {return;}
  if (xhr.status == 0) {return;} // ステータスが0の場合はクライアントによる中断の可能性があるので無視
  if (xhr.status != 200) {
    alert('アクセスエラー(' + xhr.status + ')');
    return;
  }

  // --- 5)JSONを受け取ってオブジェクト化する ------------------------
  oQty =  JSON.parse(xhr.responseText);

  // --- 6)各フォーム内の購入可能数<select>の内容を更新する ----------
  ls = Object.keys(oProd_form);
  for (i=0; i<ls.length; i++) {
    // <select name="qty">を見つける
    for (j=0; j<oProd_form[ls[i]].length; j++) {
      le = oProd_form[ls[i]][j].elements;
      e = undefined;
      for (k=0; k<le.length; k++) {
        if (le[k].name !== 'qty') {continue;}
        e = le[k];
        break;
      }
      if (e === undefined) {continue;}
      if (       e.tagName === 'SELECT') {
        // <select>の場合:0～購入可能数量まで<option>を書く
        n = (oQty['product_avail_qtys'][ls[i]]['avail'].match(/^[0-9]+$/)) ? oQty['product_avail_qtys'][ls[i]]['avail'] : 1; // 在庫無限のものは数量1固定
        while (e.firstChild) {e.removeChild(e.firstChild);}                      // <option>を一旦全削除
        for (k=0; k<=n; k++) {
          e1 = document.createElement('option');
          e1.innerHTML = k;
          if (k == oQty['product_avail_qtys'][ls[i]]['qty']) {e1.selected = true;}
          e.appendChild(e1);
        }
      } else if (e.tagName === 'INPUT' ) {
        // <input>の場合:valueプロパティーに値を代入
        e.value = oQty['product_avail_qtys'][ls[i]]['qty'];
        // カゴ入れ可能な在庫数を<input type="hidden" name="avail_qtys" />に持たせる
        n = (oQty['product_avail_qtys'][ls[i]]['avail'].match(/^[0-9]+$/)) ? oQty['product_avail_qtys'][ls[i]]['avail'] : 1; // 在庫無限のものは数量1固定
        e = undefined;
        for (k=0; k<le.length; k++) {
          if (le[k].name !== 'avail_qtys') {continue;}
          e = le[k];
          break;
        }
        if (e === undefined) {
          e = document.createElement('input');
          e.type  = 'hidden';
          e.name  = 'avail_qtys';
          e.value = 0;
          le[0].form.appendChild(e);
        }
        e.value = n;
      }
    }
  }

  // --- 7)カゴに1つ追加ボタンがあれば数量に応じて有効化・無効化する -
  ls = Object.keys(oProd_form);
  for (i=0; i<ls.length; i++) {
    // <input name="add1">を見つける
    for (j=0; j<oProd_form[ls[i]].length; j++) {
      le = oProd_form[ls[i]][j].elements;
      e = undefined;
      for (k=0; k<le.length; k++) {
        if (le[k].name !== 'add1') {continue;}
        e = le[k];
        break;
      }
      if (e === undefined) {continue;}
      // その商品IDが在庫数1以上ならボタンを有効に、0なら無効にする
      if (oQty['product_avail_qtys'][ls[i]]['avail'] !=0) {
        e.value    = 'カゴに1つ追加';
        e.disabled = false;
      } else {
        e.value    = '在庫切れ';
        e.disabled = true;
      }
    }
  }

  // --- 10)アラートメッセージがあれば表示する -----------------------
  if (oQty['alertmsg'] != "") {alert(oQty['alertmsg']);}

  // --- 99)正常終了 -------------------------------------------------
  return;
}


// ===== レジへ進むボタンの更新 ======================================
// [入力]
//   なし
// [出力]
//   ・カゴに商品が入っているか否かに応じてレジへ進むボタンのenable/disable
// [備考]
//   -
function update_goto_cashier_button() {
  var xhr;          // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/GETNUMOFITEMS.AJAX.CGI'; // AjaxのURL定義

  // --- 1)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = 'dummy='+parseInt((new Date)/1);            //キャッシュ対策

    xhr.open('POST', sUrl_ajax, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.onreadystatechange = function(){update_goto_cashier_button_callback(xhr)};
    xhr.withCredentials = true;
    xhr.send(s);
  }
}
function update_goto_cashier_button_callback(xhr) {
  var i, s;         // 汎用変数
  var eCashier;     // レジへ進むボタンエレメント

  // --- 2)アクセス成功で呼び出されたのでないなら即終了 --------------
  if (xhr.readyState != 4) {return;}
  if (xhr.status == 0) {return;} // ステータスが0の場合はクライアントによる中断の可能性があるので無視
  if (xhr.status != 200) {
    alert('アクセスエラー(' + xhr.status + ')');
    return;
  }

  // --- 3)レジへ進むボタンエレメントを取得 --------------------------
  eCashier = document.getElementById('goto_cashier');

  // --- 4)商品数が1以上ならenable、0ならdisable ---------------------
  eCashier.disabled = (xhr.responseText > 0) ? false        : true;
  eCashier.value    = (xhr.responseText > 0) ? 'レジへ進む' : 'カゴは空です';

  // --- 99)正常終了 -------------------------------------------------
  return;
}


// ===== カゴの中身表を取得する ======================================
// [入力]
//   ・bVariable_qty : 数量変更フォームを付けたい    →true
//                                       付けたくない→false
// [出力]
//   ・カゴに商品が入っているか否かに応じてレジへ進むボタンのenable/disable
// [備考]
//   -
function get_receipt_html_parts(eTable, bVariable_qty) {
  var s;            // 汎用変数
  var xhr;          // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/SHOWRECEIPT.AJAX.CGI'; // AjaxのURL定義

  // --- 1)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = 'variable=';
    s += (bVariable_qty==true)?'1':'0';
    s += '&dummy='+parseInt((new Date)/1);  //キャッシュ対策

    xhr.open('POST', sUrl_ajax, true);
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.onreadystatechange = function(){get_receipt_html_parts_callback(xhr,eTable)};
    xhr.withCredentials = true;
    xhr.send(s);
  }
}
function get_receipt_html_parts_callback(xhr, eTable) {
  // --- 2)アクセス成功で呼び出されたのでないなら即終了 --------------
  if (xhr.readyState != 4) {return;}
  if (xhr.status == 0) {return;} // ステータスが0の場合はクライアントによる中断の可能性があるので無視
  if (xhr.status != 200) {
    alert('アクセスエラー(' + xhr.status + ')');
    return;
  }

  // --- 3)指定された<table>に受け取った中身をハメ込む ---------------
  eTable.innerHTML = xhr.responseText;

  // --- 4)数量selectタグを表示する ----------------------------------
  update_product_qtys();

  // --- 5)表を表示する ----------------------------------------------
  document.getElementById('receipt_tbl').style.display = 'table';

  // --- 99)正常終了 -------------------------------------------------
  return;
}


// ===== カゴ入れ系フォームの有効・無効化 ============================
// [入力]
//   ・bConceal : 無効化するならtrue、有効化するならfalse（間違えぬこと!）
// [出力]
//   ・
// [備考]
//   ・レジへ進むボタンのconceal解除だけは、カゴに商品があるかどうかで
//     決めるべきであるため、この関数では行わない(無効化するのみ)
function cart_controls_concealer(bConceal) {
  var le,i,j,e,b;       // 汎用変数
  if(bConceal === undefined) {bConceal = true;}


  // --- 2)更新が必要なフォームを確認し、ボタンの有効無効を変える ----
  le = document.getElementsByTagName('form');
  for (i=0; i<le.length; i++) {
    if (! le[i].className.match(/\btakingform\b/)) {continue;}
    b = false;
    for (j=0; j<le[i].elements.length; j++) {
      e = le[i].elements[j];
      if (e.name  !== 'pid') {continue;}
      if (e.value === '-'  ) {continue;}
      b = true;
      break;
    }
    if (!b) {continue;}
    for (j=0; j<le[i].elements.length; j++) {
      e = le[i].elements[j];
      if (e.name  === 'add1') {e.disabled = bConceal;}
      if (e.name  === 'del' ) {e.disabled = bConceal;}
      if (e.name  === 'qty' ) {e.disabled = bConceal;}
    }
  }

  // --- 2)カゴ入れボタンの有効無効を変える --------------------------
  e = document.getElementById('goto_cashier');
  if (       (e != null) && (  bConceal)) {
    e.disabled = true;
  } else if ((e != null) && (! bConceal)) {
    //update_goto_cashier_button();
  }
}


// ###################################################################
// # レジへ進む・戻る系
// ###################################################################

// ===== Cookieとして持っているカゴID(visitorid)をCGI変数化する ======
// [入力]
// ・eForm : <form>タグのelementオブジェクト
// [出力]
// ・レジページと今のページ(商品ページ)のOriginが異なる場合は、Cookie内の
//   visitoridとtimestampを下記のようにCGI変数化する。(存在しない場合はやらない)
//   <input type="hidden" name="visitorid" value="<Cookie内のvisitorid値>" />
//   <input type="hidden" name="timestamp" value="<Cookie内のtimestamp値>" />
// ・今のページ(商品ページ)のURLを下記のようにCGI変数"referrer"にする。
//   <input type="hidden" name="referrer" value="<現ページのURL値>" />
//   (ただし、visitorid変数とtimestamp変数が含まれていたら除去する)
// [備考]
// ・この関数は、レジへ進む時に http から https に切り替わるサイトで、
//   かつドメインが替わってしまうサイトのために用意されている。そのよう
//   なサイトでは Cookie が引き継げないためである。
function create_visitorid_input(eForm) {
  var sOrigin_cas, sOrigin_now; // Origin比較用
  var e;                        // 汎用変数
  var visitorid, timestamp;     // Cookie変数値

  // --- 1)Cashierと今のOriginを求める -------------------------------
  sOrigin_cas = (eForm.action.match( /^(https?:\/\/[^/]+)/)) ? RegExp.$1 : '';
  sOrigin_now = (location.href.match(/^(https?:\/\/[^/]+)/)) ? RegExp.$1 : '';

  // --- 2)referrer用<input>タグを作る -------------------------------
  e = document.createElement('input');
  e.type  = 'hidden';
  e.name  = 'referrer';
  e.value = location.href.replace(/visitorid=\w+&?/,'').replace(/timestamp=\d+&?/,'').replace(/\?$/,'');
  eForm.appendChild(e);

  // 以下のものは、Cashierページと今のページのOriginが異なり、
  // かつ今のCookie内にvisitoridとtimestampがある場合のみ実施
  while (sOrigin_cas !== sOrigin_now) {

    // --- 3)Cookie内からvisitoridとtimestampを抽出 ------------------
    if (! document.cookie.match(/\s*visitorid=([A-Za-z0-9_]+)/)) {break;}
    visitorid = RegExp.$1;
    if (! document.cookie.match(/\s*timestamp=([0-9]{14})/)    ) {break;}
    timestamp = RegExp.$1;

    // --- 4)visitorid用<input>タグを作る ----------------------------
    e = document.createElement('input');
    e.type  = 'hidden';
    e.name  = 'visitorid';
    e.value = visitorid;

    // --- 5)timestamp用<input>タグを作る ----------------------------
    e = document.createElement('input');
    e.type  = 'hidden';
    e.name  = 'timestamp';
    e.value = timestamp;
    eForm.appendChild(e);

    // --- 6)Cookieを消す --------------------------------------------
    document.cookie = 'visitorid=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
    document.cookie = 'timestamp=; expires=Thu, 01 Jan 1970 00:00:00 GMT';

    break;
  }

  // --- 7)正常終了 --------------------------------------------------
  return;
}

// ===== 商品ページからレジページへ到着した時の処理 ==================
// [入力]
// ・なし
// [出力]
// ・商品ページとレジページのOriginが違う場合には、
//   戻るボタン等でページ移動をしようとした場合の警告イベントを設定する。
// [備考]
// ・次へ進む等、ページ内のボタンでも警告が出てしまうので、各ボタンに
//   イベント解除関数cancel_onbeforeunload_event()を仕込むこと。
function arrived_at_cashier() {
  var e;                        // 汎用変数
  var sOrigin_ref, sOrigin_now; // Origin比較用

  // --- 1)Cashierと今のOriginを求める -------------------------------
  e = document.getElementById('referrer');
  if (! e)                                    { return; }
  if (! e.value.match(/^(https?:\/\/[^/]+)/)) { return; }
  sOrigin_ref = RegExp.$1;
  sOrigin_now = (location.href.match(/^(https?:\/\/[^/]+)/)) ? RegExp.$1 : '';

  // --- 2)Originが一致していれば何もしないで終了 --------------------
  if (sOrigin_now === sOrigin_ref) { return; }

  // --- 3)ページを離れる際の警告イベント設定 ------------------------
  window.onbeforeunload = function(e) {
    var e = e || window.event;
    var sMsg = '商品ページへ戻るボタンを使わずに、別のページへ移動するとカゴの内容は破棄されます。\n(更新ボタンを押してこのメッセージが出た時は無視して構いません)';
    if (e) { e.returnValue = sMsg; }
    return sMsg;
  };
}
function cancel_onbeforeunload_event() { window.onbeforeunload = null; return true; }

// ===== レジから商品ページへ戻る時の処理 ============================
// [入力]
// ・#referrerに格納されているURL
// [出力]
// ・戻り値なし
// ・#referrerのURLにCookieから読み取ったvisitoridとtimestampを付けた
//   URLへジャンプする
// [備考]
// ・この関数は、レジへ進む時に http から https に切り替わるサイトで、
//   かつドメインが替わってしまうサイトのために用意されている。そのよう
//   なサイトでは Cookie が引き継げないためである。
function goback_from_cashier() {
  var e, s, dt, sOrigin_ref, sOrigin_now, sReferrer;

  // --- 1)商品ページURLを調べる -------------------------------------
  e = document.getElementById('referrer');
  if (! e)                                    { history.back(); return; }
  if (! e.value.match(/^(https?:\/\/[^/]+)/)) { history.back(); return; }
  sOrigin_ref = RegExp.$1;

  // --- 2)戻り先URLのドメインとSSL有無が一致していればそのまま移動して終了
  sOrigin_now = (location.href.match(/^(https?:\/\/[^/]+)/)) ? RegExp.$1 : '';
  if (sOrigin_now === sOrigin_ref) {
    document.location = e.value;
    return;
  }

  // --- 3)戻りURLを作る ---------------------------------------------
  sReferrer = e.value;
  if (document.cookie.match(/\s*visitorid=([A-Za-z0-9_]+)/)) {
    s = (sReferrer.match(/\?/)) ? '&' : '?';
    sReferrer += s + 'visitorid=' + RegExp.$1;
    dt = new Date();
    sReferrer +=    '&timestamp=';
    sReferrer += ('000'+(dt.getYear()+1900).toString()).substr(-4);
    sReferrer += (  '0'+(dt.getMonth()+1  ).toString()).substr(-2);
    sReferrer += (  '0'+(dt.getDate()     ).toString()).substr(-2);
    sReferrer += (  '0'+(dt.getHours()    ).toString()).substr(-2);
    sReferrer += (  '0'+(dt.getMinutes()  ).toString()).substr(-2);
    sReferrer += (  '0'+(dt.getSeconds()  ).toString()).substr(-2);
  }

  // --- 4)Cookieを消す ----------------------------------------------
  document.cookie = 'visitorid=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
  document.cookie = 'timestamp=; expires=Thu, 01 Jan 1970 00:00:00 GMT';

  // --- 5)商品ページへ戻る ------------------------------------------
  document.location = sReferrer;

  // --- 6)正常終了 --------------------------------------------------
  return;
}

// ===== レジから商品ページへ戻ってきた時のCookie上書き処理 ==========
// [入力]
// ・なし
// [出力]
// ・戻り値なし
// ・Query文字列にvisitorid変数とtimestamp変数があって、
//   それがCookieにある同名変数より新しい(無い場合も含む)場合には
//   Cookieにある同名変数を上書きする。
// [備考]
// ・この関数は、レジへ進む時に http から https に切り替わるサイトで、
//   かつドメインが替わってしまうサイトのために用意されている。そのよう
//   なサイトでは Cookie が引き継げないためである。
function update_cookie_when_goback_from_cashier() {
  var sQuery, visitorid_q, timestamp_q, visitorid_c, timestamp_c, sExp, sPth;

  // --- 1)Cookieが使用不可であれば何もせず終了 ----------------------
  if (! window.navigator.cookieEnabled) { return; }

  // --- 2)QueryStringからvisitoridを取得してみる --------------------
  sQuery = '&' + location.href.replace(/^[^?]+\?/,'') + '&';
  if (! sQuery.match(/&visitorid=([A-Za-z0-9_]+)&/)) { return; }
  visitorid_q = RegExp.$1;
  if (! sQuery.match(/&timestamp=([0-9]{14})&/)    ) { return; }
  timestamp_q = RegExp.$1;

  // --- 3)Cookieからvisitoridを取得してみる -------------------------
  if (document.cookie.match(/\s*visitorid=([A-Za-z0-9_]+)/)) {
    visitorid_c = RegExp.$1;
  }
  if (document.cookie.match(/\s*timestamp=([0-9]{14})/)    ) {
    timestamp_c = RegExp.$1;
  } else {
    timestamp_c = '00000000000000';
  }

  // --- 4)Query由来とCookie由来のタイムスタンプを比較し、 -----------
  //       Query由来の方が古ければ何もしないで終了
  if (timestamp_q*1 < timestamp_c) { return; }

  // --- 5)Cookie上書き処理 ------------------------------------------
  sExp = '; expires='+(new Date(((new Date()).getTime()+86400000))).toUTCString();
  sPth = '; path=/';
  document.cookie = 'visitorid=' + visitorid_q + sExp + sPth;
  document.cookie = 'timestamp=' + timestamp_q + sExp + sPth;

  // --- 6)正常終了 --------------------------------------------------
  return;
}


// ###################################################################
// # ローディングメッセージ表示
// ###################################################################

// ===== ローディングメッセージカバー作成 ============================
// [入力]
//   なし
// [出力]
//   なし
// [備考]
// ・不透明度0で作成されるので、後記のfadein関数を使って表示させること。
function loading_cover_make() {
  var eCover_msg, eCover;

  eCover_msg = document.getElementById('loading_cover_msg');
  if (eCover_msg == null) {
    eCover_msg = document.createElement('p');
    eCover_msg.id                  = 'loading_cover_msg';
    eCover_msg.style.width         = '300px';
    eCover_msg.style.position      = 'absolute';
    eCover_msg.style.top           = '50%';
    eCover_msg.style.left          = '50%';
    eCover_msg.style.marginTop     = '-2em';
    eCover_msg.style.marginBottom  = '0';
    eCover_msg.style.marginLeft    = '-150px';
    eCover_msg.style.marginRight   = '0';
    eCover_msg.style.paddingTop    = '0';
    eCover_msg.style.paddingBottom = '0';
    eCover_msg.style.paddingLeft   = '0';
    eCover_msg.style.paddingRight  = '0';
    eCover_msg.style.lineHeight    = '1.5em';
    eCover_msg.style.textAlign     = 'center';
    eCover_msg.style.fontWeight    = 'bold';
    eCover_msg.style.color         = '#ffffff';
    eCover_msg.innerHTML           = 'ただいま処理中です。<br />しばらくお待ちください。<br /><img src="'+get_homedir()+'HTML/img/LOADING_BAR.GIF" alt="Now loading"/>';
  }

  eCover = document.getElementById('loading_cover');
  if (eCover == null) {
    eCover = document.createElement('div');
    eCover.id                    = 'loading_cover';
    eCover.style.width           = document.documentElement.clientWidth                           +'px';
    eCover.style.height          = document.documentElement.clientHeight                          +'px';
    eCover.style.position        = 'absolute';
    eCover.style.zIndex          = '1';
    eCover.style.backgroundColor = '#000000';
  }
  eCover.style.top               = (document.documentElement.scrollTop ||document.body.scrollTop )+'px';
  eCover.style.left              = (document.documentElement.scrollLeft||document.body.scrollLeft)+'px';
  if (       typeof eCover.style.opacity    !== 'undefined') {
    eCover.style.opacity    = 0;
  } else if (typeof eCover.style.MozOpacity !== 'undefined') {
    eCover.style.MozOpacity = 0;
  } else if (typeof eCover.style.filter     !== 'undefined') {
    eCover.style.filter     = 'alpha(opacity=0)';
  }

  eCover.appendChild(eCover_msg);
  document.getElementsByTagName('body').item(0).appendChild(eCover);

  loading_cover_sizeupdate(0.1);
}


// ===== ローディングメッセージカバーサイズ更新 ======================
// [入力]
//   iInterval: 更新頻度(秒)
// [出力]
//   なし
// [備考]
// ・カバーが常にブラウザ画面内を覆い隠すように、iInterval秒毎にサイズ
//   更新する。
// ・#loading_coverが存在する限り、本関数は再実行される。
function loading_cover_sizeupdate(iInterval) {
  var eCover = document.getElementById('loading_cover');

  if (eCover == null) {return;}

  eCover.style.width  = document.documentElement.clientWidth                           +'px';
  eCover.style.height = document.documentElement.clientHeight                          +'px';
  eCover.style.top    = (document.documentElement.scrollTop ||document.body.scrollTop )+'px';
  eCover.style.left   = (document.documentElement.scrollLeft||document.body.scrollLeft)+'px';

  setTimeout('loading_cover_sizeupdate('+iInterval+')',Math.round(iInterval*1000));
}


// ===== ローディングメッセージカバーフェードイン ====================
// [入力]
//   iOpacity  : 不透明度(0～1)
//   iStartDate: フェードイン開始日時(UNIX時間)
//   iEndDate  : フェードイン完了日時(UNIX時間)
//   iInterval : 不透明度更新間隔インターバル(秒)
// [出力]
//   なし
// [備考]
// ・iEndDateの日時に達するまで、本関数はiInterval秒ごとに再実行される。
// ・ただし#loading_coverが存在しなくなったら、本関数は終了する。
function loading_cover_fadein(iOpacity, iStartDate, iEndDate, iInterval) {
  var iOffset_time, iCur_opacity, eCover;

  eCover = document.getElementById('loading_cover');
  if (eCover == null) {return;}

  iOffset_time = iEndDate - new Date().getTime()/1000;
  if (iOffset_time > 0) {
    iCur_opacity = Math.round(iOpacity*(iEndDate-iStartDate-iOffset_time)/(iEndDate-iStartDate)*100)/100;
    setTimeout('loading_cover_fadein('+iOpacity+','+iStartDate+','+iEndDate+','+iInterval+')',Math.round(iInterval*1000));
  } else {
    iCur_opacity = Math.round(iOpacity*100)/100;
  }

  if (typeof eCover.style.opacity           !== 'undefined') {
    eCover.style.opacity    = iCur_opacity;
  } else if (typeof eCover.style.MozOpacity !== 'undefined') {
    eCover.style.MozOpacity = iCur_opacity;
  } else if (typeof eCover.style.filter     !== 'undefined') {
    eCover.style.filter     = 'alpha(opacity='+(iCur_opacity*100)+')';
  }
}


// ===== ローディングメッセージカバー削除 ============================
// [入力]
//   なし
// [出力]
//   なし
function loading_cover_remove() {
  var eBody      = document.getElementsByTagName('body').item(0);
  var eCover     = document.getElementById('loading_cover'     );
  var eCover_msg = document.getElementById('loading_cover_msg' );

  if ((eCover != null)&&(eCover_msg != null)) {eCover.removeChild(eCover_msg);}
  if (eBody  != null)                         {eBody.removeChild(eCover)     ;}
}



// ###################################################################
// # その他
// ###################################################################

// ===== 郵便番号による住所検索ボタン ================================
// [入力]
// ・id="inqZipcode1"とid="inqZipcode2"の値
// [出力]
// ・見つかった場合
//   - id="inqPref"な<select>の都道府県を選択
//   - id="inqCity"な<input>に市区町村名を出力
//   - id="inqTown"な<input>に町名を出力
// ・見つからなかった場合
//   - alertメッセージ
// [備考]
function zipcode_to_address() {
  var e, s;         // 汎用変数
  var sZipcode;     // フォームから取得した郵便番号文字列の格納用
  var xhr;          // XML HTTP Requestオブジェクト格納用
  var sUrl_ajax = get_homedir() + 'CGI/ZIP2ADDR.AJAX.CGI';  // AjaxのURL定義

  // --- 1)郵便番号を取得する ----------------------------------------
  e = document.getElementById('inqZipcode1');
  e.value = e.value.replace(/[０-９]/g,function(s){return String.fromCharCode(s.charCodeAt(0)-0xFEE0);});
  if (! e.value.match(/^([0-9]{3})$/)) {
    alert('郵便番号(前の3桁)が正しくありません');
    return;
  }
  sZipcode = "" + RegExp.$1;
  e = document.getElementById('inqZipcode2');
  e.value = e.value.replace(/[０-９]/g,function(s){return String.fromCharCode(s.charCodeAt(0)-0xFEE0);});
  if (! e.value.match(/^([0-9]{4})$/)) {
    alert('郵便番号(後の4桁)が正しくありません');
    return;
  }
  sZipcode = "" + sZipcode + RegExp.$1;


  // --- 2)Ajaxコール ------------------------------------------------
  xhr = createXMLHttpRequest();
  if (xhr) {
    s  = sUrl_ajax;
    s += '?zipcode='+sZipcode;
    s += '&dummy='+parseInt((new Date)/1);               //キャッシュ対策

    xhr.open('GET', s, true);
    xhr.onreadystatechange = function(){zipcode_to_address_callback(xhr)};
    xhr.send(null);
  }
}
function zipcode_to_address_callback(xhr) {

  var oAddress; // サーバーからの戻り値
  var e;        // 汎用変数

  // --- 3)アクセス成功で呼び出されたのでないなら即終了 --------------
  if (xhr.readyState != 4) {return;}
  if (xhr.status == 0    ) {return;} // ステータスが0の場合はクライアントによる中断の可能性があるので無視
  if      (xhr.status == 400) {
    alert('郵便番号が正しくありません');
    return;
  }
  else if (xhr.status != 200) {
    alert('アクセスエラー(' + xhr.status + ')');
    return;
  }

  // --- 4)サーバーから返された住所データを格納 ----------------------
  oAddress = JSON.parse(xhr.responseText);
  if (oAddress['zip'] === '') {
    alert('対応する住所が見つかりませんでした');
    return;
  }

  // --- 5)都道府県名を選択する --------------------------------------
  e = document.getElementById('inqPref')
  for (i=0; i<e.options.length; i++) {
    if (e.options.item(i).value == oAddress['pref']) {
      e.selectedIndex = i;
      break;
    }
  }

  // --- 6)市区町村名を流し込む --------------------------------------
  document.getElementById('inqCity').value = oAddress['city'];

  // --- 7)町名を流し込む --------------------------------------------
  document.getElementById('inqTown').value = oAddress['town'];

  // --- 99)正常終了 -------------------------------------------------
  return;
}
