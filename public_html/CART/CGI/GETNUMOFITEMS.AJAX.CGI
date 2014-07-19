#! /bin/sh

######################################################################
#
# GETNUMOFITEMS.AJAX.CGI
# かごの中の商品数を得る
# Written by Matsuura(richmikan@richlab.org) at 2012/11/09
#
# [入力]
# ・[Cookie文字列]
#   - visitorid: カゴのID
# [出力]
# ・かごの中の商品数(種類の数であって、1つの商品を複数個でも1と数える)
# [備考]
# ・このスクリプトは、有効なセッションが無い場合、新規作成はしない。
#
######################################################################


######################################################################
# 初期設定
######################################################################

# --- このシステム(CART)のホームディレクトリー -----------------------
Homedir="$(d=${0%/*}/; [ "_$d" = "_$0/" ] && d='./'; cd "$d.."; pwd)"

# --- その他初期ディレクトリー等定義 ---------------------------------
# 1)Tukubaiパス、その他共通定義
. $Homedir/CONFIG/COMMON.SHLIB  
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi

# --- エラー終了関数定義 ---------------------------------------------
errorcode_exit() {
  cat <<-__HTTP_HEADER
	Status: 500 Internal Server Error
	Content-Type: text/plain

	500 Internal Server Error
	($@)
__HTTP_HEADER
  [ -n "$Tmp" ] && rm -f $Tmp*
  exit 1
}
dyingmessage() {
  printf 'Content-Type: text/plain\n\n'
  echo "$@"
  exit
}

# --- 走行ログ記録開始設定 -------------------------------------------
if [ -z "$DISABLE_SHLOG" ]; then
  timestamp=$(date '+%Y%m%d %H%M%S')
  timestamp_date=${timestamp% *}
  timestamp_time=${timestamp#* }
  Execlogdir=$Dir_LOG/${timestamp_date%[0-9][0-9][0-9][0-9]}/${timestamp_date#[0-9][0-9][0-9][0-9]}/CGI
  ([ "$SUEXEC_MODE" -eq 0 ] && umask 0000; mkdir -p "$Execlogdir")
  [ $? -eq 0 ] || errorcode_exit 'log directory is not available'
  touch "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || errorcode_exit 'Fail to create a logfile'
  [ "$SUEXEC_MODE" -eq 0 ] && chmod go+r "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  gzpipe $Tmp-gzlogpipe "$Execlogdir/${0##*/}.$timestamp_time.$$.log.gz"
  [ $? -eq 0 ] || errorcode_exit 'Fail to create a pipe for logging'
  exec 2> $Tmp-gzlogpipe
  set -xv
fi


######################################################################
# メイン0(プリフライト)
######################################################################

# === メイン0 ここから(実行は、OPTIONSメソッドの場合のみ) ============
if [ "${REQUEST_METHOD:-_}" = 'OPTIONS' ]; then

# --- 成功フラグをリセットし、breakdown区間にする --------------------
correct=0
while [ 1 ]; do

# --- 許可されたOriginか? --------------------------------------------
cat $Homedir/CONFIG/ALLOWED_ORIGIN_LIST.TXT |
env - sed 's/^#.*$//'                       | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'       | # コメント除去2
grep -v '^[[:blank:]]*$'                    | # 空行除去
awk '$1=="'"$(echo "_${HTTP_ORIGIN:-.}" | sed '1s/^_//' | tr -d '"')"'"{ret=1} END{exit 1-ret}'
[ $? -eq 0 ] || break

# --- Access-Control-Request-Method検査(POSTであること) --------------
echo "_${HTTP_ACCESS_CONTROL_REQUEST_METHOD:-_}" |
sed '1s/^_//'                                    |
head -n 1                                        |
awk 'toupper($0)!="POST"{exit 1}'                > /dev/null
[ $? -eq 0 ] || break

# --- ここまで来たらOPTIONSリクエストは合格 --------------------------
correct=1

# --- breakdown区間ここまで ------------------------------------------
break
done

# --- 成否に応じてHTTPヘッダー送出 -----------------------------------
if [ $correct -gt 0 ]; then
  cat <<-__HTTP_OK
	Access-Control-Allow-Origin: $HTTP_ORIGIN
	Access-Control-Allow-Methods: POST, OPTIONS
	Access-Control-Max-Age: $((COOKIE_LIFELIMIT_MIN*60))
	Access-Control-Allow-Credentials: true
	Content-Length: 0
	Content-Type: text/plain

__HTTP_OK
else
  cat <<-__HTTP_NG
	Status: 400 Bad Request
	Content-Type: text/plain

	400 Bad Request
__HTTP_NG
fi

# --- メイン0はここで終了 --------------------------------------------
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0

# === メイン0 ここまで ===============================================
fi


######################################################################
# メイン
######################################################################

# --- リファラーチェック ---------------------------------------------
cat $Homedir/CONFIG/ALLOWED_ORIGIN_LIST.TXT |
env - sed 's/^#.*$//'                       | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'       | # コメント除去2
grep -v '^[[:blank:]]*$'                    | # 空行除去
awk '
  # ALLOWED_ORIGIN_LIST.TXTに列挙されているOriginのどれかで始まっているならOK
  BEGIN {
    ref = "'"$(echo "_${HTTP_REFERER:--}" | sed '1s/^_//' | tr -d '"')"'";
  }
  {
    s = (length(ref)>length($1)) ? substr(ref,1,length($1)) : ref;
    if (s == $1) {ret=1; exit;}
  }
  END {
    exit 1-ret;
  }'
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

# --- Cookieを取得 ---------------------------------------------------
echo "_${HTTP_COOKIE:-}"         |
sed '1s/^_//'                    |
sed 's/&/%26/g'                  |
sed 's/[;,[:blank:]]\{1,\}/\&/g' |
sed 's/^&//; s/&$//'             |
cgi-name                         > $Tmp-cookie

# --- visitorid(セッションIDに相当)に基づきセッションファイル確保 ----
visitorid=$(nameread visitorid $Tmp-cookie | tr -Cd 'A-Za-z0-9_.-')
File_session=$(sessionf reuse "$Dir_SESSION/$visitorid" lifemin=$COOKIE_LIFELIMIT_MIN)
[ $? -eq 0 ] || { visitorid='.'; File_session=$Tmp-dummysession; }

# --- Cross-Origin Resource Sharing 対応 -----------------------------
# 環境変数HTTP_ORIGINと等しい文字列の行が ALLOWED_ORIGIN_LIST.TXT の中にあったら
# CORSに対応した2つのHTTPヘッダーを生成する
cors=''
cat $Homedir/CONFIG/ALLOWED_ORIGIN_LIST.TXT |
env - sed 's/^#.*$//'                       | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//'       | # コメント除去2
grep -v '^[[:blank:]]*$'                    | # 空行除去
awk '$1=="'"$(echo "_${HTTP_ORIGIN:-.}" | sed '1s/^_//' | tr -d '"')"'"{ret=1} END{exit 1-ret}'
if [ $? -eq 0 ]; then
  cors=$(printf '\nAccess-Control-Allow-Origin: %s\nAccess-Control-Allow-Credentials: true' "$HTTP_ORIGIN")
fi

# --- Cookieの寿命分だけ延長した日時を得る(dummy sessionでない場合) --
if [ "_$visitorid" != '_.' ]; then
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
fi

# --- HTTPヘッダー送信 -----------------------------------------------
cat <<-HTTP_HEADER
	Content-Type: text/plain$cors$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

HTTP_HEADER

# --- かごの中の商品数送信 -------------------------------------------
zcat "$File_session"                          |
grep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+$' | # 商品名以外を除去
gyo                                           |
tr -d '\n'

# --- 正常終了 -------------------------------------------------------
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
