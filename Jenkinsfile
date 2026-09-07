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
    // Not localhost: Jenkins is itself a container with its own network
    // namespace, so its localhost is Jenkins, not the Pi, and the host port
    // mapping is unreachable from in here — the smoke check spent every deploy
    // being refused in 0 ms. Both containers sit on the shared `proxy`
    // network, so the app answers to its own name.
    HEALTH_URL = 'http://nicolas-arias-web-app:7000/health'
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
    // `not slow` is the repository's own name for everything that does not
    // drive a real browser — the same selection `make test-fast` runs. The
    // browser suites are excluded on purpose: this machine is an ARM Pi that
    // is building Docker images while the tests run, and two consecutive
    // deploys were blocked there by two different browser tests that pass on
    // every other machine, in GitHub Actions and locally alike. Whatever that
    // flake turns out to be, a browser on a loaded Pi is not where it gets
    // decided, and a site does not stay down over it. GitHub Actions runs the
    // full 116 on every pull request; the Smoke stage below is what proves
    // this particular deploy is alive.
    stage('Tests') {
      steps {
        sh """
          docker rm -f ${TEST_CONTAINER} || true
          docker run --name ${TEST_CONTAINER} ${TEST_IMAGE} \
            python3 -m pytest -v --tb=short -m 'not slow' tests/
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
          for attempt in \$(seq 1 20); do
            if curl -fsS ${HEALTH_URL} > /dev/null; then
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
