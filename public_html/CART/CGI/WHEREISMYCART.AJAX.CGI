#! /bin/sh

######################################################################
#
# WHEREISMYCART.AJAX.CGI
# カート取得プログラム
# Written by Rich Mikan(richmikan@richlab.org) at 2014/07/21
#
# [入力]
#    [HTTP Cookieで次の変数を与える]
#      visitorid  : 買い物かごID
# [出力]
#    ・標準出力にて0を返す。(1以上を返して失敗することはない)
#    ・visitoridが来ればそれに対応するカゴの存在を確認し、あればCookieで教える。
#      そして、有効なvisitoridが来なければ新規発行してCookieで教える。
#
# [備考]
#    ・これはサードパーディーCookieをSafariで回避するためのもので
#      支店サイトのWebページには、次のようなものを設置して使う。
#      <form id="whereismycart" method="GET" action="(*)" target="ifr">
#        <input type="hidden"  name="cookiewrite" value="cookiewritevalue" />
#      </form>
#      <iframe name="ifr"></iframe>
#      <script type="text/javascript">
#      <!--
#        document.getElementById('whereismycart').submit();
#      //-->
#      </script>
#        :
#    ・上記ソースコードの(*)部分に次のようなURLを入れる
#      https://honten.example.com/CART/CGI/WHEREISMYCART.AJAX.CGI
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
visitorid=${File_session##*/}

# --- The Platform for Privacy Preferences (P3P)対応 -----------------
p3p=$(printf "\nP3P: CP='UNI CUR OUR'")

# --- Cookieの寿命分だけ延長した日時を得る(dummy sessionでない場合) --
if [ "_$visitorid" != '_.' ]; then
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
fi

# --- HTTPヘッダー送信 -----------------------------------------------
cat <<-HTML_HEADER
	Content-Type: text/plain$p3p$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

HTML_HEADER

# --- HTTPボディー送信 -----------------------------------------------
echo -n 0

# --- 正常終了 -------------------------------------------------------
pid=$(cat $Tmp-sessionfilelockid)
[ -n "$pid" ] && kill -s TERM $pid
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
