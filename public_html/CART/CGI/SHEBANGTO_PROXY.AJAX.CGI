#! /bin/sh

######################################################################
#
# SHEBANGTO_PROXY.AJAX.CGI
# 支店からSH番頭本店サイトAJAXへのPROXY
# Written by Matsuura(richmikan@richlab.org) at 2013/11/09
#
# [入力]
#    HTTP POSTで次の変数を与える
#      ・本CGIで必要なもの
#        cmd : 呼び出す本店Ajax名
#      ・その他、呼び出すAjaxに必要なCGI変数
#    [HTTP Cookieで次の変数を与える]
#      visitorid  : 買い物かごID
# [出力]
#    ・cmdの指定が不正だったり、登録されているAjaxでない場合ではない場
#      合は HTTP 400 エラー
#    ・本店へのアクセスに失敗した場合は HTTP 500 エラー
#    ・それ以外の場合は本店で呼び出したAjaxの仕様に準拠するレスポンスを
#      返す。
#
# [備考]
#    このCGIは、Tukubaiコマンドを使っておらず、curlコマンドさえあれば
#    動作する。これは、支店サイトへのSH番頭デプロイの労力を最小限に抑
#    えるためである。
#
######################################################################


######################################################################
# 初期設定(このCGIの使用者は必ず目を通すこと)
######################################################################

# --- 支店サイトでカゴ入れボタンを設置するページの最上位ディレクトリーパス
# (Cookieのセキュリティーに配慮するならば設定すべき)
cookie_scope_dir='/'

# --- 走行ログをとる場合は、ログディレクトリーを指定する -------------
Dir_LOG=''


######################################################################
# 初期設定(システム)
######################################################################

# --- 本店AJAXのあるURLへのプレフィックス ----------------------------
url_prefix='http://example.org/CART/CGI/'

# --- 許容される本店Ajax名を設定 -------------------------------------
allowed_ajaxes='ADDTOCART.AJAX.CGI GETNUMOFITEMS.AJAX.CGI SHOWQTYS.AJAX.CGI SHOWRECEIPT.AJAX.CGI SIGNEDINPANEL.AJAX.CGI'

# --- 自分のホームディレクトリーとそこからのパス ---------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d"; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
Tmp=/tmp/${0##*/}-$$            # テンポラリーファイルプレフィックス
ACK=$(printf '\006')            # エスケープ文字
LF=$(printf '\\\n_');LF=${LF%_} # sedコマンド用の改行置換コード

# --- エラー終了関数定義 ---------------------------------------------
errorcode_exit() {
  cat <<-__HTTP_HEADER
	Status: 500 Internal Server Error
	Content-Type: text/plain

	500 Internal Server Error
	($@)
__HTTP_HEADER
  [ -n "$Tmp" ] && rm -f $Tmp-*
  exit 1
}
errorcode_exit_400() {
  cat <<-__HTTP_HEADER
	Status: 400 Bad Request
	Content-Type: text/plain

	400 Bad Request
	($@)
__HTTP_HEADER
  [ -n "$Tmp" ] && rm -f $Tmp-*
  exit 1
}
dyingmessage() {
  printf 'Content-Type: text/plain\n\n'
  echo "$@"
  exit
}

# --- 走行ログ記録開始設定 -------------------------------------------
if [ -d "$Dir_LOG" ]; then
  timestamp=$(date '+%Y%m%d %H%M%S')
  timestamp_date=${timestamp% *}
  timestamp_time=${timestamp#* }
  Execlogdir=$Dir_LOG/${timestamp_date%[0-9][0-9][0-9][0-9]}/${timestamp_date#[0-9][0-9][0-9][0-9]}/CGI
  (umask 0000; mkdir -p "$Execlogdir")
  [ $? -eq 0 ] || errorcode_exit 'log directory is not available'
  exec 2> "$Execlogdir/${0##*/}.$timestamp_time.$$.log"
  set -xv
fi


######################################################################
# クライアントから送られてきたリクエストのValidation
######################################################################

# --- CGI変数(POST)の受け取り ----------------------------------------
dd bs=${CONTENT_LENGTH:-0} count=1 2>/dev/null > $Tmp-rawcgivars

# --- リファラーチェック ---------------------------------------------
# 支店のOriginと同じかどうかチェック
s=$(echo "_${HTTP_REFERER:--}"                              |
    sed '1s/^_//'                                           |
    sed 's/^\(https\{0,1\}:\/\/[A-Za-z0-9.-]\{1,\}\).*$/\1/')
case "${HTTPS:-off}" in [Oo][Nn]) s1="https://${SERVER_NAME:-}";; *) s1="http://${SERVER_NAME:-}";; esac
[ "_$s" = "_$s1" ]
if [ $? -ne 0 ]; then
  cat <<-__HTTP_NG
	Status: 400 Bad Request
	Content-Type: text/plain

	Web browsers have to send referer correctly to trade with me.
	Check the setting of your web browser.
__HTTP_NG
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 0

fi

# --- 本店呼び出しAjaxの確認・抽出 -----------------------------------
cat $Tmp-rawcgivars                                   |
tr '&' '\n'                                           |
awk '                                                 # 冒頭のシェル変数
  BEGIN {                                             # $allowed_ajaxes
    split("'"$allowed_ajaxes"'",allowed_ajaxes);      # で指定した本店Ajaxの
    ok = 0;                                           # いずれかが、
    cmd_is_already_existent = 0;                      # CGI変数"cmd"にて正しく
    cmd = "";                                         # 指定されている場合のみ
  }                                                   # 戻り値0とし、かつ
  /^cmd=/ {                                           # "cmd"以外のCGI変数を
    if (cmd_is_already_existent!=0) {ok=0; exit;}     # 出力する。
    s = substr($0,5);                                 # (それ以外は、
    gsub(/%2[Dd]/, "-"); gsub(/%2[Ee]/, ".");         # 戻り値1以上)
    if (! match(s,/^[A-Za-z0-9_.-]+$/)) {ok=0; exit;} #
    for (i in allowed_ajaxes) {                       # ただし、1行目は
      if (allowed_ajaxes[i] == s) {                   # 本店Ajax名が
        cmd = s;                                      # 入っているので、
        ok = 1;                                       # curlに渡すのは
        next;                                         # 2行目だけにすること。
      }                                               #
    }                                                 #
    ok=0; exit;                                       #
  }                                                   #
  {                                                   #
    vars[NR] = $0;                                    #
  }                                                   #
  END {                                               #
    if (ok != 0) {                                    #
      print cmd;                                      #
      ORS = "";                                       #
      s   = "";                                       #
      for (i in vars) {print s vars[i]; s="&";}       #
    }                                                 #
    exit 1-ok;                                        #
  }'                                                  > $Tmp-rawcgivars2
[ $? -eq 0 ] || errorcode_exit_400 'Invalid Ajax call'

# --- クライアントからサーバーへのCookieがあればcookieオプションを生成
visitorid_cookie=$(echo "_${HTTP_COOKIE:-}"             |
                   sed '1s/^_//'                        |
                   sed 's/[;[:blank:]]\{1,\}/'"$LF"'/g' |
                   grep '^visitorid=[A-Za-z0-9_.-]\+$'  |
                   head -n 1                            )
if [ -n "$visitorid_cookie" ]; then
  opt_cookie="-b $visitorid_cookie"
else
  opt_cookie=''
fi


######################################################################
# 本店サーバーと通信
######################################################################

# --- 本店へアクセス -------------------------------------------------
url="${url_prefix%/}/$(head -n 1 $Tmp-rawcgivars2)"
tail -n +2 $Tmp-rawcgivars2                  |
curl -d @- -D $Tmp-http-response-header $url > $Tmp-http-response-body
[ $? -eq 0 ] || errorcode_exit 'fail to connect the head store'


######################################################################
# クライアントへレスポンス送信
######################################################################

# --- 受信したヘッダーから送信用のヘッダーを作成して送信 -------------
cat $Tmp-http-response-header                                                 |
awk '                                                                         #
  /^HTTP\/[0-9.]+ / {                                                         #
    status = "Status: " substr($0,match($0, " ")+1);                          #
    next;                                                                     #
  }                                                                           #
  /^Content-Type: /i {                                                        #
    content_type = $0;                                                        #
    next;                                                                     #
  }                                                                           #
  /^Set-Cookie: visitorid=/i {                                                #
    setcookie_visitorid = $0;                                                 #
    sub(/[:;][^[:blank:]]*path=/, "&'"$ACK"'", setcookie_visitorid);          #
    sub(/'"$ACK"'[^[:blank:]]+/, "'"$cookie_scope_dir"'", setcookie_visitorid);
    next;                                                                     #
  }                                                                           #
  END {                                                                       #
    print status;                                                             #
    print setcookie_visitorid;                                                #
    print content_type;                                                       #
    print "Cache-Control: private, no-store, no-cache, must-revalidate";      #
    print "Pragma: no-cache";                                                 #
  }'

# --- 受信したボディーを送信 -----------------------------------------
cat $Tmp-http-response-body


######################################################################
# 正常終了
######################################################################

[ -n "$Tmp" ] && rm -f $Tmp-*
exit 0
