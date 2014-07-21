#! /bin/sh

######################################################################
#
# ADDTOCART.AJAX.CGI
# 商品追加プログラム
# Written by Rich Mikan(richmikan@richlab.org) at 2013/11/09
#
# [入力]
#    HTTP POSTで次のCGI変数を与える
#      pid : 商品ID
#      qty : 個数
#    [HTTP Cookieで次の変数を与える]
#      visitorid  : 買い物かごID
# [出力]
#    標準出力にて、成功すれば0、失敗すれば1以上を返す
#
# [備考]
#    商品を取り消したい場合は、個数0で実行すればよい
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
  pid=$(cat $Tmp-sessionfilelockid)
  [ -n "$pid" ] && kill -s TERM $pid
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

# --- CGI変数(POST)を取得 --------------------------------------------
dd bs=${CONTENT_LENGTH:-0} count=1 2>/dev/null |
sed 's/+/%20/g'                                |
cgi-name                                       > $Tmp-cgivars

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

# --- CGI変数チェック&変数格納 ---------------------------------------
grep '^pid[[:blank:]][A-Za-z0-9_.-]\+$' $Tmp-cgivars > /dev/null
[ $? -eq 0 ] || errorcode_exit 'pid_is_not_given'
reqpid=$(nameread pid $Tmp-cgivars)
grep '^qty[[:blank:]][0-9]\+$' $Tmp-cgivars > /dev/null
[ $? -eq 0 ] || errorcode_exit 'qty_is_not_given'
reqqty=$(expr $(nameread qty $Tmp-cgivars) + 0)

# --- 要求された商品が、サーバー上に登録されているものかどうか確認 ---
[ -f "$File_PRODUCTS" ] || errorcode_exit 'Productmaster_not_found'
grep '^'"$reqpid"'[[:blank:]]' "$File_PRODUCTS" > /dev/null 2>&1
[ $? -eq 0 ] || errorcode_exit 'no_such_product_found'

# --- Cookieを取得 ---------------------------------------------------
printf '%s' "${HTTP_COOKIE:-}"   |
sed 's/&/%26/g'                  |
sed 's/[;,[:blank:]]\{1,\}/\&/g' |
sed 's/^&//; s/&$//'             |
cgi-name                         > $Tmp-cookie

# --- visitorid(セッションIDに相当)に基づきセッションファイル確保 ----
visitorid=$(nameread visitorid $Tmp-cookie | tr -Cd 'A-Za-z0-9_.-')
File_session=$(sessionf avail "$visitorid" "at=$Dir_SESSION/XXXXXXXXXXXXXXXXXXXXXXXX" lifemin=$COOKIE_LIFELIMIT_MIN)
[ $? -eq 0 ] || errorcode_exit 'cannot_create_session_file'
exflock 10 "$File_session" > $Tmp-sessionfilelockid # 多重アクセス防止
if [ "$visitorid" != "${File_session##*/}" ]; then
  newsession='yes'
  visitorid=${File_session##*/}
fi

# === (これより breakdown 区間) =======================================
failure=0
while [ 1 ]; do

# --- 取引対象商品在庫数は足りているかどうか確認 ---------------------
GET_STOCKQTYS.SH $reqpid > $Tmp-currentstock
[ $? -eq 0 ] || errorcode_exit 'Cannot_check_stock_quantity'
curqty=$(cat $Tmp-currentstock | self 2)
if [ \( $curqty != '*' \) -a \( $curqty -lt $reqqty \) ]; then
  failure=1
  break
fi

# --- セッションファイルの中身を更新する -----------------------------
zgrep -v "^$reqpid[[:blank:]]" "$File_session" >  $Tmp-newsessionfile
echo "$reqpid $reqqty"                         |
awk '$2>0'                                     >> $Tmp-newsessionfile
cat $Tmp-newsessionfile |
gzip                    > "$File_session"
[ $? -eq 0 ] || errorcode_exit 'Failed_to_update_the_session_file'

break; done
# === (breakdown 区間ここまで)========================================

# --- The Platform for Privacy Preferences (P3P)対応 -----------------
p3p=$(printf "\nP3P: CP='UNI CUR OUR'")

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

# --- セキュリティ向上のため,セッションIDを付け替える ----------------
while [ -z "${newsession:-}" ]; do
  s=$(sessionf renew "$visitorid" "at=$Dir_SESSION/XXXXXXXXXXXXXXXXXXXXXXXX" lifemin=$COOKIE_LIFELIMIT_MIN)
  [ $? -eq 0 ] || break # 一時ファイル生成に失敗したら付け替えは諦める
  File_session=$s
  visitorid=${s##*/}
  break
done

# --- Cookieの寿命分だけ延長した日時を得る(dummy sessionでない場合) --
if [ "_$visitorid" != '_.' ]; then
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
fi

# --- HTTPヘッダー送信 -----------------------------------------------
cat <<-HTML_HEADER
	Content-Type: text/plain$p3p$cors$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

HTML_HEADER

# --- HTTPボディー送信 -----------------------------------------------
echo -n $failure

# --- 正常終了 -------------------------------------------------------
pid=$(cat $Tmp-sessionfilelockid)
[ -n "$pid" ] && kill -s TERM $pid
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
