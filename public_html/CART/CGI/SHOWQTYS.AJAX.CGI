#! /bin/sh

######################################################################
#
# SHOWQTYS.AJAX.CGI
# ・指定された商品群について
#   (1)買い物かごに入れられる数量
#   (2)今買い物かごに入っている数量
#   を各々返す。
# ・在庫不足になった場合には不足商品のカゴ入り数も減らす。
# Written by Matsuura(richmikan@richlab.org) at 2013/11/09
#
# [入力]
# ・HTTP POSTで次のCGI変数を与える
#     pids : 知りたい商品IDをカンマ区切りで列挙する
# ・[HTTP Cookieで次の変数を与える]
#     visitorid  : 買い物かごID
# [出力]
# ・下記のJSON構造体で返す
#     {"product_avail_qtys" :
#        {
#          "<商品ID>": {"avail":"<購入可能数量>", "qty":<カゴに入っている数量>},
#          "<商品ID>": {"avail":"<購入可能数量>", "qty":<カゴに入っている数量>},
#                          :
#                          :
#        },
#      "alertmsg": "<在庫不足になった場合の詳細メッセージ>"
#     }
#   - JavaScriptで取り出したい時はこうやる("hoge1"の場合)
#     hoge['product_avail_qtys']['hoge1']['avail']
#     hoge['product_avail_qtys']['hoge1']['qty']
# [備考]
#  ・実際の在庫数$TR_REMAIN_BORDERを超える場合はTR_REMAIN_BORDERを数量
#    として返す。
#  ・電子版などの在庫数無限商品については<数量>="*"として返す。
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
. $Homedir/CONFIG/COMMON.SHLIB  # Tukubaiパス、その他共通定義
. $Homedir/CONFIG/TRADING.SHLIB # 取引ルール定義
# 2)ファイルは基本的に自分だけ読み書き可能にする
umask 066
# 3)一時ファイルのベースを作る
Tmp=$(mkstemp /tmp/${0##*/}.XXXXXXXXXXXXXXXXXXXXXXXX)
if [ \( $? -ne 0 \) -o \( -z "$Tmp" \) ]; then
  echo "${0##*/}: Cannot make tempfiles" 1>&2; exit 1
fi
# 4)特殊文字等
ACK=$(printf '\006')            # スペースエスケープ用の変数
NAK=$(printf '\025')            # タブエスケープ用の変数

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

# --- Cookieを取得 ---------------------------------------------------
printf '%s' "${HTTP_COOKIE:-}"   |
sed 's/&/%26/g'                  |
sed 's/[;,[:blank:]]\{1,\}/\&/g' |
sed 's/^&//; s/&$//'             |
cgi-name                         > $Tmp-cookie

# --- visitorid(セッションIDに相当)に基づきセッションファイル確保 ----
visitorid=$(nameread visitorid $Tmp-cookie | tr -Cd 'A-Za-z0-9_.-')
File_session=$(sessionf reuse "$Dir_SESSION/$visitorid" lifemin=$COOKIE_LIFELIMIT_MIN)
[ $? -eq 0 ] || { visitorid='.'; File_session=$Tmp-dummysession; }

# --- そのユーザーの現在商品各かご入れ数を得る -----------------------
zcat "$File_session"                          |
grep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+$' | # 商品名以外を除去
sort -k1,1                                    > $Tmp-havingqtys
# 1:商品ID 2:現在カゴいれ数
[ $(gyo $Tmp-havingqtys) -eq 0 ] && echo '. 0' > $Tmp-havingqtys # カゴが空だったらダミーデータを入れる

# --- CGI変数読み込み→「現在カゴ入れ数,現在庫数表」を作成 -----------
GET_STOCKQTYS.SH . $(cat $Tmp-cgivars          | # CGI変数の        # 現在庫数を求める
                     nameread pids             | # product_idsを抽出し
                     tr , '\n'                 | # 商品IDとして正しいものだけ
                     grep -v '[^A-Za-z0-9_.-]' | # 引数に送る
                     tr '\n' ' '               ) 2>/dev/null            |
# 1:商品ID* 2:現在庫数(無限の場合は"*")                                 #
awk '$2~/^[0-9]+$/ && $2>'$TR_REMAIN_BORDER'{$2='$TR_REMAIN_BORDER'} 1' | # 上限値以上をカット
# 1:商品ID* 2:現在庫数($TR_REMAIN_BORDER以上は$TR_REMAIN_BORDERとする)  #
#join2 +0 key=1 $Tmp-havingqtys                                          > $Tmp-curqtytbl
join -1 1 -2 1 -a 2 -o 2.1,1.2,2.2 $Tmp-havingqtys -                    |
sed 's/  / 0 /'                                                         > $Tmp-curqtytbl
# 1:商品ID* 2:現在カゴ入れ数 3:現在庫数(無限の場合は"*")

# --- 在庫数超過メッセージを作成(超過商品があれば) -------------------
# 1)商品マスターを正規化しておく(1:商品ID* 2:商品名(mojihameエスケープ))
[ -f "$File_PRODUCTS" ] || errorcode_exit 'The product master file is not found'
cat "$File_PRODUCTS"                  |
env - sed 's/^#.*$//'                 | # コメント除去1
env - sed 's/[[:blank:]]\{1,\}#.*$//' | # コメント除去2
grep -v '^[[:blank:]]*$'              | # 空行除去
sort -k1,1                            |
self 1 2                              > $Tmp-productname
#   1:商品ID 2:商品名(mojihameエスケープ)
# 2)メッセージ作成
msg=$(cat $Tmp-curqtytbl                                 |
      awk '$3~/^[0-9]+$/'                                | # 無限在庫品は除外
      awk '$2>$3'                                        | # 超過商品だけ抽出
      #join1 key=1 $Tmp-productname                       |
      join -1 -2 1 -o 2.1,1.2,2.2,2.3 $Tmp-productname - |
      # 1:商品ID* 2:商品名(mojihameエスケープ) 3:現在カゴ入れ数 4:現在庫数(無限の場合は"*")
      self 2                                             |
      sed 's/\\_/'$ACK'/g'                               | # 商品名を横に並べる
      tr _ ' '                                           | #  :
      sed 's/\\\(.\)/\1/g'                               | #  :
      tr $ACK '_'                                        | #  :
      tr '\n' "$ACK"                                     | #  :
      sed 's/'"$ACK"'$//'                                | #  :
      sed 's/'"$ACK"'/, /g'                              ) #  :
[ -n "$msg" ] && msg='申し訳ありません。次の商品の在庫数がご要望の数量を下回りました。\\n('"$msg"')'

# --- 超過数を考慮してセッションファイルのカゴ入れ数を更新 -----------
# 1)カゴ入れ商品以外の情報を新セッションファイルにコピー
zcat "$File_session"                                    |
grep -v '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+$'        >  $Tmp-newsessionfile
# 2)カゴ入れ商品情報行のカゴ入れ数を、超過数を考慮して更新
zcat "$File_session"                                    |
grep '^[A-Za-z0-9_.-]\+[[:blank:]]\+[0-9]\+$'           |
#join2 '+*' key=1 $Tmp-curqtytbl                         |
join -1 1 -2 1 -a 2 -o 2.1,1.2,1.3,2.2 $Tmp-curqtytbl - |
sed 's/  / * /'                                         |
sed 's/  / * /'                                         |
# 1:商品ID 2:現在カゴ入れ数(こちらではなく4を使うこと) 3:現在庫数(無限orに表に無い場合は"*") 4:現在カゴ入れ数
awk '$3~/^[0-9]+$/ && $3<$4{$4=$3} $4>0{print $1,$4}'   >> $Tmp-newsessionfile
# 1:商品ID 4:現在カゴ入れ数(修正済)
# 3)セッションファイルを上書き更新
cat $Tmp-newsessionfile |
gzip                    > "$File_session"
[ $? -eq 0 ] || errorcode_exit 'Failed_to_update_the_session_file'

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
  cors=$(printf '\nP3P: CP='"'"'UNI CUR OUR'"'"'\nAccess-Control-Allow-Origin: %s\nAccess-Control-Allow-Credentials: true' "$HTTP_ORIGIN")
fi

# --- Cookieの寿命分だけ延長した日時を得る(dummy sessionでない場合) --
if [ "_$visitorid" != '_.' ]; then
  now=$(date -u '+%Y%m%d%H%M%S')
  cookie_str=$(printf 'visitorid %s\ntimestamp %s\n' "$visitorid" "$now"    |
               TZ=UTC+0 mkcookie -e$now+$((COOKIE_LIFELIMIT_MIN*60)) -p/ -sA)
fi

# --- HTTPヘッダー送信 -----------------------------------------------
cat <<-HTML_HEADER
	Content-Type: application/json; charset=utf-8$cors$cookie_str
	Cache-Control: private, no-store, no-cache, must-revalidate
	Pragma: no-cache

HTML_HEADER

# --- JSONの作成&送信 ------------------------------------------------
cat $Tmp-curqtytbl                                                                       |
# 1:商品ID* 2:現在カゴ入れ数(超過数の訂正前のもの) 3:現在庫数(無限の場合は"*")           #
awk 'BEGIN{print "{\"product_avail_qtys\":{"; dlm=" ";                                   }  # JSON作成(ヘッダー)
     $3~/^[0-9]+$/ && $2>$3 {$2=$3;                                                      }  # (超過分の訂正)
          {printf("%s\"%s\":{\"avail\":\"%s\", \"qty\":\"%s\"}\n",dlm,$1,$3,$2); dlm=",";}  # JSON作成(ボディー)
     END  {print "},\"alertmsg\":\"'"$(echo "_$msg" | sed '1s/^_//; s/"/\\"/g')"'\"}";   }' # JSON作成(フッター)

# --- 正常終了 -------------------------------------------------------
[ -n "$Tmp" ] && rm -f $Tmp*
exit 0
