#!/bin/bash -e

function install_wagon(){
    pip install wagon==0.2.5
}

function wagon_create_package(){
    wagon create -s http://github.com/cloudify-cosmo/cloudify-fabric-plugin/archive/$PLUGINS_TAG_NAME.tar.gz -r . --validate -v -f
}

function upload_to_s3() {
    ###
    # This will upload both the artifact and md5 files to the relevant bucket.
    # Note that the bucket path is also appended the version.
    ###
    # no preserve is set to false only because preserving file attributes is not yet supported on Windows.

    file=$(basename $(find . -type f -name "$1"))
    date=$(date +"%a, %d %b %Y %T %z")
    acl="x-amz-acl:public-read"
    content_type='application/x-compressed-exe'
    string="PUT\n\n$content_type\n$date\n$acl\n/$AWS_S3_BUCKET/$AWS_S3_PATH/$file"
    signature=$(echo -en "${string}" | openssl sha1 -hmac "${AWS_ACCESS_KEY}" -binary | base64)
    curl -v -X PUT -T "$file" \
      -H "Host: $AWS_S3_BUCKET.s3.amazonaws.com" \
      -H "Date: $date" \
      -H "Content-Type: $content_type" \
      -H "$acl" \
      -H "Authorization: AWS ${AWS_ACCESS_KEY_ID}:$signature" \
      "https://$AWS_S3_BUCKET.s3.amazonaws.com/$AWS_S3_PATH/$file"
}

function print_params(){

    declare -A params=( ["VERSION"]=$VERSION ["PRERELEASE"]=PRERELEASE ["BUILD"]=$BUILD \
                        ["CORE_TAG_NAME"]=$CORE_TAG_NAME ["PLUGINS_TAG_NAME"]=$PLUGINS_TAG_NAME \
                        ["AWS_S3_BUCKET_PATH"]=$AWS_S3_BUCKET_PATH ["PLUGIN_NAME"]=$PLUGIN_NAME \
                        ["GITHUB_USERNAME"]=$GITHUB_USERNAME ["AWS_ACCESS_KEY_ID"]=$AWS_ACCESS_KEY_ID)
    for param in "${!params[@]}"
    do
            echo "$param - ${params["$param"]}"
    done
}


# VERSION/PRERELEASE/BUILD must be exported as they is being read as an env var by the cloudify-agent-packager
export VERSION="3.3.0"
export PRERELEASE="m7"
export BUILD="277"
CORE_TAG_NAME="3.3m7"
PLUGINS_TAG_NAME="1.3m7"

#env Variables
GITHUB_USERNAME=$1
GITHUB_PASSWORD=$2
AWS_ACCESS_KEY_ID=$3
AWS_ACCESS_KEY=$4
AWS_S3_BUCKET_PATH="gigaspaces-repository-eu/org/cloudify3/${VERSION}/${PRERELEASE}-RELEASE"
PLUGIN_NAME=$5



print_params
install_wagon
wagon_create_package
cd /tmp && md5sum=$(md5sum -t *.tar.gz) && echo $md5sum > ${md5sum##* }.md5 &&
[ -z ${AWS_ACCESS_KEY} ] || upload_to_s3 "*.tar.gz:" && upload_to_s3 "*.md5"
