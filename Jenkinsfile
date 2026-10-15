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
        }
      }
    }
    stage('Source checks') {
      steps { sh 'bash ci/check-source.sh' }
    }
    stage('Build and scan') {
      steps { sh 'bash ci/build-image.sh' }
    }
    stage('External quality gates') {
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
