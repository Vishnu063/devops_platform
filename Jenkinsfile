// Alternative CI runner. Deployment is a reviewed GitOps change, not a kubectl push.
pipeline {
  agent { label 'docker' }
  options {
    timestamps()
    disableConcurrentBuilds()
    timeout(time: 20, unit: 'MINUTES')
  }
  environment {
    IMAGE = "ghcr.io/vishnu063/devops_platform"
  }
  stages {
    stage('Checkout') {
      steps { checkout scm }
    }
    stage('Test') {
      steps {
        sh '''
          docker run --rm -v "$WORKSPACE:/src" -w /src python:3.12-slim sh -c 'pip install -r requirements-dev.txt && coverage run --source=app -m unittest discover -s tests -v && coverage xml && coverage report --fail-under=80'
        '''
      }
    }
    stage('Secrets and SAST') {
      steps {
        sh '''
          docker run --rm -v "$WORKSPACE:/repo" zricethezav/gitleaks:v8.24.3 git /repo --redact --exit-code 1
          docker run --rm -v "$WORKSPACE:/src" semgrep/semgrep:1.140.0 semgrep scan --config /src/.semgrep.yml --error /src/app
        '''
      }
    }
    stage('SonarQube quality gate') {
      steps {
        withCredentials([string(credentialsId: 'sonar-token', variable: 'SONAR_TOKEN')]) {
          sh '''
            test -n "$SONAR_HOST_URL"
            docker run --rm -e SONAR_TOKEN -e SONAR_HOST_URL -v "$WORKSPACE:/usr/src" sonarsource/sonar-scanner-cli:11 -Dsonar.qualitygate.wait=true
          '''
        }
      }
    }
    stage('Build and scan') {
      steps {
        sh '''
          docker build --build-arg APP_VERSION="$GIT_COMMIT" -t "$IMAGE:$GIT_COMMIT" .
          docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.67.2 image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "$IMAGE:$GIT_COMMIT"
        '''
        withCredentials([string(credentialsId: 'snyk-token', variable: 'SNYK_TOKEN')]) {
          sh '''
            docker run --rm -e SNYK_TOKEN -v /var/run/docker.sock:/var/run/docker.sock snyk/snyk:docker snyk container test "$IMAGE:$GIT_COMMIT" --severity-threshold=high
          '''
        }
      }
    }
    stage('Publish main') {
      when { branch 'main' }
      steps {
        withCredentials([usernamePassword(credentialsId: 'ghcr', usernameVariable: 'GH_USER', passwordVariable: 'GH_TOKEN')]) {
          sh '''
            set +x
            export DOCKER_CONFIG="$(mktemp -d)"
            trap 'rm -rf "$DOCKER_CONFIG"' EXIT
            printf '%s' "$GH_TOKEN" | docker login ghcr.io -u "$GH_USER" --password-stdin
            docker push "$IMAGE:$GIT_COMMIT"
          '''
        }
      }
    }
  }
  post {
    always { archiveArtifacts artifacts: 'coverage.xml', allowEmptyArchive: true }
  }
}
