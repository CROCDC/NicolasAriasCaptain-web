pipeline {
  agent any

  environment {
    COMPOSE_FILE = 'docker-compose.yml'
    // Named rather than --rm so anything the run leaves behind can be copied out.
    TEST_CONTAINER = 'arias-tests'
    // Named outright: `config --images` lists every service, and its order is
    // not the same across compose versions, so picking the first line ran the
    // suite inside promtail once a second service existed.
    TEST_IMAGE = 'nicolas-arias-web-app'
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
    //
    // The image drives Firefox, and the committed visual baseline is
    // Chromium's, so the screenshot comparisons write a Firefox set and skip
    // rather than compare against another browser's pixels. Committing
    // tests/screenshots/linux-firefox/ from a run of this image is what turns
    // them on here; the layout is checked in GitHub Actions meanwhile, which
    // installs Chromium for exactly that reason.
    stage('Tests') {
      steps {
        sh """
          docker rm -f ${TEST_CONTAINER} || true
          docker run --name ${TEST_CONTAINER} ${TEST_IMAGE} python3 -m pytest -v --tb=short tests/
        """
      }
      post {
        always {
          sh "docker rm -f ${TEST_CONTAINER} || true"
        }
      }
    }

    // Secrets reach the container only here, as environment for the `up`:
    // SECRET_KEY signs the session cookie and lives in Infisical, so an
    // unparameterised build (INFISICAL_PROJECT_ID empty) would start the site
    // with an empty signing key rather than fail — hence the explicit guard.
    stage('Deploy') {
      steps {
        script {
          def projectId = params.INFISICAL_PROJECT_ID?.trim()
          if (projectId) {
            withCredentials([
              string(credentialsId: 'infisical-client-id',     variable: 'INFISICAL_CLIENT_ID'),
              string(credentialsId: 'infisical-client-secret', variable: 'INFISICAL_CLIENT_SECRET')
            ]) {
              sh """
                INFISICAL_TOKEN=\$(INFISICAL_DISABLE_UPDATE_CHECK=true \
                  infisical login --method=universal-auth \
                    --client-id="\$INFISICAL_CLIENT_ID" \
                    --client-secret="\$INFISICAL_CLIENT_SECRET" \
                    --domain=https://infisical.nexttech.com.ar \
                    --plain --silent)
                INFISICAL_DISABLE_UPDATE_CHECK=true \
                INFISICAL_TOKEN="\$INFISICAL_TOKEN" \
                infisical run --env prod --projectId ${projectId} \
                  --domain=https://infisical.nexttech.com.ar \
                  -- docker compose -f ${COMPOSE_FILE} up -d --remove-orphans
              """
            }
          } else {
            error("INFISICAL_PROJECT_ID is empty — refusing to deploy without SECRET_KEY.")
          }
        }
      }
    }

    // The site has to answer, not merely be running: a container that boots and
    // then 500s on every request is still "up".
    stage('Smoke') {
      steps {
        sh """
          for attempt in 1 2 3 4 5 6 7 8 9 10; do
            if curl -fsS http://localhost:7000/health > /dev/null; then
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
