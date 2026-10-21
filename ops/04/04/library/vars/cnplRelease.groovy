def call(Map config) {
    if (!(config.language in ['java', 'rust', 'c', 'cpp', 'csharp', 'jsts', 'python'])) {
        error('Unsupported language')
    }
    properties([disableConcurrentBuilds(), parameters([string(name: 'SOURCE_REVISION', description: 'Approved full source SHA')])])
    if (!(params.SOURCE_REVISION ==~ /[a-f0-9]{40}/)) { error('Full source SHA required') }
    timeout(time: 60, unit: 'MINUTES') {
        input message: "Publish reviewed ${config.language} commit ${params.SOURCE_REVISION}?", submitter: 'cnpl-release-approvers'
        node("cnpl-release-${config.language}") {
            deleteDir()
            checkout([$class: 'GitSCM', branches: [[name: params.SOURCE_REVISION]], userRemoteConfigs: [[url: config.sourceUrl, credentialsId: 'source-readonly']]])
            withEnv(["LANGUAGE=${config.language}", 'CI_FLAVOR=jenkins', "SOURCE_REVISION=${params.SOURCE_REVISION}", "PIPELINE_URL=${env.BUILD_URL}", "SOURCE_DIR=ops/04/05/examples/${config.language}"]) {
                try {
                    stage('Verify') { container('builder') { sh 'bash ops/04/05/build.sh "$LANGUAGE"' } }
                    container('tools') {
                        stage('Package') {
                            withCredentials([file(credentialsId: 'buildkit-ca', variable: 'BUILDKIT_CA'), file(credentialsId: 'buildkit-client-cert', variable: 'BUILDKIT_CERT'), file(credentialsId: 'buildkit-client-key', variable: 'BUILDKIT_KEY'), file(credentialsId: 'harbor-auth', variable: 'HARBOR_AUTH'), file(credentialsId: 'nexus-release', variable: 'NEXUS_CURL_CONFIG')]) {
                                sh 'set +x; export DOCKER_CONFIG=$(mktemp -d); trap \'rm -rf -- "$DOCKER_CONFIG"\' EXIT; cp "$HARBOR_AUTH" "$DOCKER_CONFIG/config.json"; bash ops/04/03/shared/package.sh'
                            }
                        }
                        stage('Supply chain') {
                            withCredentials([file(credentialsId: 'cosign-key', variable: 'COSIGN_KEY_FILE'), file(credentialsId: 'cosign-password', variable: 'COSIGN_PASSWORD_FILE'), file(credentialsId: 'harbor-auth', variable: 'HARBOR_AUTH')]) {
                                sh 'set +x; export DOCKER_CONFIG=$(mktemp -d); trap \'rm -rf -- "$DOCKER_CONFIG"\' EXIT; cp "$HARBOR_AUTH" "$DOCKER_CONFIG/config.json"; bash ops/04/08/supply-chain.sh'
                            }
                        }
                        stage('Propose GitOps') {
                            withCredentials([file(credentialsId: 'gitops-token', variable: 'GITOPS_TOKEN_FILE'), file(credentialsId: 'gitops-api', variable: 'GITOPS_CURL_CONFIG')]) {
                                sh 'bash ops/04/03/shared/gitops.sh'
                            }
                        }
                        stage('Observe approved merge') {
                            input message: 'Merge the reviewed GitOps MR, then observe deployment', submitter: 'cnpl-release-approvers'
                            withCredentials([file(credentialsId: 'argocd-readonly', variable: 'ARGOCD_CONFIG'), file(credentialsId: 'app-health', variable: 'APP_CURL_CONFIG')]) {
                                sh 'bash ops/04/03/shared/observe.sh'
                            }
                        }
                    }
                } finally {
                    archiveArtifacts artifacts: 'release/**,ops/04/05/examples/*/dist/**', allowEmptyArchive: true
                    deleteDir()
                }
            }
        }
    }
}
