pipeline {
  agent any

  environment {
    COMPOSE_FILE = 'docker-compose.yml'
    // Named rather than --rm so anything the run leaves behind can be copied out.
    TEST_CONTAINER = 'arias-tests'
  }

  stages {
    stage('Parse Commit Message') {
      steps {
        script {
          def commitMessage = sh(returnStdout: true, script: "git log -1 --pretty=%B").trim()
          env.FORCE_REBUILD = commitMessage.contains("FORCE_REBUILD") ? "true" : "false"
          env.FULL_CLEAN    = commitMessage.contains("FULL_CLEAN")    ? "true" : "false"
        }
      }
    }

    // Reclaims disk without touching what is serving: taking the app down here
    // would leave the site off for the length of a build that may not pass.
    stage('Clean') {
      when { expression { return env.FULL_CLEAN == "true" } }
      steps {
        sh "docker builder prune -f || true"
        sh "docker image prune -f || true"
      }
    }

    stage('Build') {
      steps {
        script {
          def buildCmd = "docker compose -f ${COMPOSE_FILE} build"
          if (env.FORCE_REBUILD == "true") {
            buildCmd += " --no-cache"
          }
          sh buildCmd
        }
      }
    }

    // The gate runs on the image that is about to ship, before anything is
    // deployed: a failure here has to leave the running site alone. The
    // container is a throwaway off that image and shares nothing with
    // production — no ports, no database volume, no secrets.
    stage('Tests') {
      steps {
        sh """
          docker rm -f ${TEST_CONTAINER} || true
          IMAGE=\$(docker compose -f ${COMPOSE_FILE} config --images | head -1)
          docker run --name ${TEST_CONTAINER} "\$IMAGE" python3 -m pytest -v --tb=short tests/
        """
      }
      post {
        always {
          sh "docker rm -f ${TEST_CONTAINER} || true"
        }
      }
    }

    stage('Deploy') {
      steps {
        sh "docker compose -f ${COMPOSE_FILE} up -d --remove-orphans"
      }
    }

    // The site has to answer, not merely be running: a container that boots and
    // then 500s on every request is still "up".
    stage('Smoke') {
      steps {
        sh """
          for attempt in 1 2 3 4 5 6 7 8 9 10; do
            if curl -fsS http://localhost:7003/health > /dev/null; then
              echo "healthy"
              exit 0
            fi
            sleep 3
          done
          echo "the app never answered /health"
          exit 1
        """
      }
    }
  }

  post {
    failure {
      echo "Build failed — the running site was left as it was."
    }
  }
}
