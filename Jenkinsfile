// Trusted main branch only. Jenkins uses the same checks as GitHub Actions.
// Publication is deliberately owned by the GitHub release workflow.
pipeline {
  agent { label 'docker' }
  options {
    timestamps()
    skipDefaultCheckout(true)
    disableConcurrentBuilds()
    timeout(time: 45, unit: 'MINUTES')
  }
  parameters {
    booleanParam(name: 'RUN_LIVE_RELEASE_CHECK', defaultValue: false,
      description: 'Trusted main only; requires administrator-configured private runner, credentials and target/report variables')
  }
  stages {
    stage('Trust boundary') {
      when { not { branch 'main' } }
      steps { error('Run this credentialed pipeline only on trusted main.') }
    }
    stage('Checkout') {
      steps {
        deleteDir()
        checkout scm
        script {
          env.GIT_SHA = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
          env.SKIP_TOOLKIT_CI = sh(script: 'git log -1 --format=%B', returnStdout: true).contains('[skip ci]').toString()
        }
      }
    }
    stage('Toolkit configuration checks') {
      when { expression { env.SKIP_TOOLKIT_CI != 'true' } }
      steps {
        sh "python3 -m venv .venv-toolkit && .venv-toolkit/bin/python -m pip install '.[yaml]'"
        sh 'TOOLKIT_PYTHON=.venv-toolkit/bin/python bash ci/offline-checks.sh'
      }
    }
    stage('Source checks') {
      when { expression { env.SKIP_TOOLKIT_CI != 'true' } }
      steps { sh 'bash ci/check-source.sh' }
    }
    stage('Build and scan') {
      when { expression { env.SKIP_TOOLKIT_CI != 'true' } }
      steps { sh 'bash ci/build-image.sh' }
    }
    stage('Live release check (explicit opt-in)') {
      when { expression { env.SKIP_TOOLKIT_CI != 'true' && params.RUN_LIVE_RELEASE_CHECK } }
      steps {
        withCredentials([file(credentialsId: 'toolkit-kubeconfig', variable: 'TOOLKIT_KUBECONFIG')]) {
          sh 'set +x; KUBECONFIG="$TOOLKIT_KUBECONFIG" TOOLKIT_PYTHON=.venv-toolkit/bin/python bash ci/live-release-check.sh'
        }
      }
    }
    stage('External quality gates') {
      when { expression { env.RUN_EXTERNAL_GATES == 'true' } }
      steps {
        withCredentials([
          string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN'),
          string(credentialsId: 'snyk-token', variable: 'SNYK_TOKEN')
        ]) {
          sh 'set +x; bash ci/external-gates.sh'
        }
      }
    }
  }
  post {
    always {
      archiveArtifacts artifacts: 'coverage.xml,reports/**', allowEmptyArchive: true
    }
    cleanup { deleteDir() }
  }
}
